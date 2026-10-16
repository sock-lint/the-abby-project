"""Deploy verified current main through Coolify without changing app configuration."""

import ipaddress
import json
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SHA = re.compile(r"[0-9a-f]{40}")
UUID = re.compile(r"[A-Za-z0-9_-]+")
TRANSIENT_HTTP = frozenset((408, 429, 500, 502, 503, 504))
ACTIVE = frozenset(("queued", "in_progress"))
TERMINAL = frozenset(("finished", "failed", "cancelled-by-user"))


class DeploymentError(Exception):
    """An actionable failure whose message contains no API response or secret."""


class DeploymentInterrupted(DeploymentError):
    pass


class ConnectionFailure(DeploymentError):
    """The request outcome is unknown; this never authorizes a POST replay."""


class InvalidResponse(DeploymentError):
    pass


class ApiError(DeploymentError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"API request returned HTTP {status}; check token permissions and endpoint configuration.")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        # Never forward the Bearer credential to a redirected endpoint.
        return None


class JsonApi:
    def __init__(self, base_url, token=None):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.netloc
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise DeploymentError("API/health URL must be an absolute HTTP(S) URL without credentials or query parameters.")
        if parsed.scheme == "http":
            try:
                address = ipaddress.ip_address(parsed.hostname)
            except ValueError:
                raise DeploymentError("Plain HTTP API access requires an explicit private LAN IP address.") from None
            if not any(address in ipaddress.ip_network(network) for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")):
                raise DeploymentError("Plain HTTP API access is restricted to private LAN addresses.")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, method, path="", body=None):
        headers = {"Accept": "application/json", "User-Agent": "abby-deploy-platform", "Cache-Control": "no-cache"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            # Error bodies and deployment logs can contain private configuration.
            raise ApiError(error.code) from None
        except (URLError, TimeoutError, ConnectionError, HTTPException):
            raise ConnectionFailure("API request failed; check runner connectivity and API availability.") from None
        except (ValueError, UnicodeError):
            raise InvalidResponse("API returned invalid JSON; check endpoint configuration.") from None


@dataclass(frozen=True)
class Config:
    sha: str
    repository: str
    application_uuid: str
    timeout: int = 1200
    poll_interval: int = 10


def check_application(application, config):
    if not isinstance(application, dict) or application.get("uuid") != config.application_uuid:
        raise DeploymentError("Coolify returned a different application UUID.")
    repository = application.get("git_repository", "").removesuffix(".git").rstrip("/")
    if repository not in (config.repository, f"https://github.com/{config.repository}", f"git@github.com:{config.repository}"):
        raise DeploymentError("Coolify application repository differs from this GitHub repository.")
    if application.get("git_branch") != "main":
        raise DeploymentError("Coolify application must target main.")
    if application.get("git_commit_sha") not in ("HEAD", config.sha):
        raise DeploymentError("Coolify application is pinned to another commit; review its configuration before deploying.")


def current_main(github, repository):
    result = github.request("GET", f"/repos/{repository}/git/ref/heads/main")
    sha = result.get("object", {}).get("sha") if isinstance(result, dict) else None
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise DeploymentError("GitHub did not return a valid current-main SHA.")
    return sha


def cancel_deployment(coolify, deployment_uuid):
    try:
        coolify.request("POST", f"/deployments/{deployment_uuid}/cancel")
        print(f"Cancelled deployment {deployment_uuid}.", flush=True)
    except DeploymentError:
        print(f"Cancellation could not be confirmed for {deployment_uuid}; inspect this deployment in Coolify.", file=sys.stderr, flush=True)


def temporary(error):
    return isinstance(error, ConnectionFailure) or isinstance(error, ApiError) and error.status in TRANSIENT_HTTP


def check_deadline(deadline, clock):
    if clock() >= deadline:
        raise DeploymentError("Coolify deployment exceeded its deadline; inspect its queue and build status.")


def read_with_retry(operation, deadline, clock, sleep, before_retry=None):
    """Retry an observational GET only; callers must never pass a mutation."""
    for attempt in range(5):
        check_deadline(deadline, clock)
        try:
            result = operation()
            check_deadline(deadline, clock)
            return result
        except DeploymentError as error:
            if not temporary(error):
                raise
            check_deadline(deadline, clock)
            if attempt == 4:
                raise DeploymentError("Temporary API failures persisted after bounded read retries; inspect runner connectivity.") from None
            print("Temporary API failure; retrying an observation without queuing another deployment.", flush=True)
            sleep(min(2 ** (attempt + 1), max(0, deadline - clock())))
            check_deadline(deadline, clock)
            if before_retry:
                before_retry()


def deployment_history(get, config):
    history = get(f"/deployments/applications/{config.application_uuid}?take=50")
    if not isinstance(history, dict) or not isinstance(history.get("deployments"), list):
        raise DeploymentError("Coolify returned invalid application deployment history.")
    return history["deployments"]


def normal_deployment(deployment, config):
    # The application-scoped history route is the ownership proof. Explicit
    # contradictory UUID fields must still never be accepted.
    return (isinstance(deployment, dict) and deployment.get("pull_request_id", 0) in (0, None)
            and all(deployment.get(field, config.application_uuid) == config.application_uuid
                    for field in ("resource_uuid", "application_uuid")))


def deployment_id(deployment):
    uuid = deployment.get("deployment_uuid", "")
    if not isinstance(uuid, str) or not UUID.fullmatch(uuid):
        raise DeploymentError("Coolify returned an invalid deployment UUID; inspect its queue.")
    return uuid


def active_deployment(history, config):
    active = [row for row in history if normal_deployment(row, config) and row.get("status") in ACTIVE]
    if len(active) > 1:
        raise DeploymentError("Multiple active application deployments are ambiguous; inspect its queue before retrying.")
    if not active:
        return None
    if active[0].get("commit") not in (config.sha, "HEAD"):
        raise DeploymentError("Another commit has an active application deployment; inspect its queue before retrying.")
    return deployment_id(active[0])


def reconcile_deployment(get, config, baseline, deadline, clock, sleep):
    """An uncertain POST is observed, never replayed, even if no row appears."""
    while clock() < deadline:
        candidates = {}
        for row in deployment_history(get, config):
            if not normal_deployment(row, config):
                continue
            uuid = deployment_id(row)
            if uuid in baseline:
                continue
            status, commit = row.get("status"), row.get("commit")
            if ((status in ACTIVE and commit in (config.sha, "HEAD"))
                    or (status in TERMINAL and commit == config.sha)):
                candidates[uuid] = row
        if len(candidates) > 1:
            raise DeploymentError("Deployment request outcome is ambiguous; inspect this application's queue. No replacement request was sent.")
        if candidates:
            return next(iter(candidates))
        sleep(min(config.poll_interval, max(0, deadline - clock())))
    raise DeploymentError("Deployment request outcome could not be confirmed; inspect this application's queue. No replacement request was sent.")


def deploy(config, coolify, latest_main, health, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + config.timeout
    read = lambda operation, until=deadline, guard=None: read_with_retry(operation, until, clock, sleep, guard)
    current = lambda: read(latest_main)
    get = lambda path: read(lambda: coolify.request("GET", path))

    def ensure_current():
        if current() != config.sha:
            raise DeploymentError("This deployment was superseded on main; a new workflow must deploy the latest commit.")

    if current() != config.sha:
        print("Skipping deployment: this workflow commit is no longer current main.", flush=True)
        return False
    check_application(get(f"/applications/{config.application_uuid}"), config)
    history = deployment_history(get, config)
    baseline = {deployment_id(row) for row in history if isinstance(row, dict)}
    deployment_uuid = active_deployment(history, config)
    # Recheck immediately before the only deployment mutation. Coolify 4.1.2's
    # API resolves HEAD itself and has no immutable commit input.
    if current() != config.sha:
        print("Skipping deployment: main changed during application verification.", flush=True)
        return False
    finished = False
    cancel_eligible = deployment_uuid is not None
    previous_status = None
    checked_uuid = False

    def reconcile():
        until = min(deadline, clock() + 60)
        return reconcile_deployment(lambda path: read(lambda: coolify.request("GET", path), until),
                                    config, baseline, until, clock, sleep)

    try:
        if deployment_uuid is None:
            check_deadline(deadline, clock)
            try:
                # Never retry this mutation: an error can follow acceptance.
                result = coolify.request("POST", "/deploy", {"uuid": config.application_uuid, "force": False})
                deployments = result.get("deployments", []) if isinstance(result, dict) else []
                if (not isinstance(deployments, list) or len(deployments) != 1
                        or not isinstance(deployments[0], dict)
                        or deployments[0].get("resource_uuid") != config.application_uuid):
                    raise InvalidResponse("Coolify did not return one deployment for the configured application.")
                try:
                    deployment_uuid = deployment_id(deployments[0])
                    cancel_eligible = True
                except DeploymentError:
                    raise InvalidResponse("Coolify did not return a valid deployment UUID.") from None
            except DeploymentError as error:
                if not temporary(error) and not isinstance(error, InvalidResponse):
                    raise
                print("Deployment request outcome is uncertain; reconciling application history without resubmitting.", flush=True)
                deployment_uuid = reconcile()
                cancel_eligible = True
        print(f"Monitoring deployment {deployment_uuid} for commit {config.sha}.", flush=True)
        while clock() < deadline:
            try:
                deployment = read(lambda: coolify.request("GET", f"/deployments/{deployment_uuid}"), guard=ensure_current)
            except ApiError as error:
                # Coolify 4.1.2's duplicate deploy response may name a newly
                # generated UUID instead of its existing queue row. Resolve
                # only a new compatible row in this application's history.
                if error.status == 404 and not checked_uuid:
                    # The API's phantom UUID is also an uncertain outcome.
                    # Reconcile new rows, including a fast exact-SHA finish.
                    cancel_eligible = False
                    deployment_uuid = None
                    deployment_uuid = reconcile()
                    cancel_eligible = True
                    checked_uuid = True
                    continue
                raise
            checked_uuid = True
            if (not isinstance(deployment, dict) or deployment.get("deployment_uuid") != deployment_uuid
                    or not normal_deployment(deployment, config)):
                # Contradictory ownership invalidates earlier proof. Never
                # cancel a cross-application, preview, or different UUID even
                # when a preceding response associated it with this app.
                cancel_eligible = False
                raise DeploymentError("Coolify returned conflicting deployment identity; inspect this application's queue. Cancellation was withheld.")
            status = deployment.get("status")
            commit = deployment.get("commit")
            finished = status in TERMINAL
            if status != previous_status:
                if status not in ACTIVE | TERMINAL:
                    raise DeploymentError("Coolify returned an unknown deployment status; inspect this deployment.")
                print(f"Deployment status: {status}.", flush=True)
                previous_status = status
            if commit not in (None, "", "HEAD") and commit != config.sha:
                raise DeploymentError("Coolify resolved a different commit; this workflow will not accept that deployment.")
            ensure_current()
            if status == "finished":
                finished = True
                if commit != config.sha:
                    raise DeploymentError("Finished deployment did not prove the exact expected commit; inspect its resolved commit.")
                break
            if status in ("failed", "cancelled-by-user"):
                finished = True
                raise DeploymentError(f"Coolify deployment {status}; inspect this deployment in Coolify.")
            sleep(min(config.poll_interval, max(0, deadline - clock())))
        else:
            check_deadline(deadline, clock)
    finally:
        if cancel_eligible and deployment_uuid and not finished:
            cancel_deployment(coolify, deployment_uuid)

    health_deadline = min(deadline, clock() + 120)
    while clock() < health_deadline:
        ensure_current()
        try:
            result = read(lambda: health.request("GET"), health_deadline, ensure_current)
        except InvalidResponse:
            # A proxy/container can briefly return plaintext `ok` during
            # rollout. It proves no identity; only this health wait tolerates
            # invalid JSON, within the same bounded verification window.
            result = None
        ensure_current()
        check_deadline(health_deadline, clock)
        if (isinstance(result, dict) and result.get("status") == "ok" and result.get("db") == "up"
                and result.get("commit") == config.sha and result.get("resourceUuid") == config.application_uuid):
            print(f"Coolify finished commit {config.sha}; public serving identity, application and database are healthy.", flush=True)
            return True
        sleep(min(config.poll_interval, max(0, health_deadline - clock())))
    raise DeploymentError("Deployment finished, but public /health did not confirm the exact serving commit, application and database within its deadline.")


def main():
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise DeploymentError("Production deployment requires the main ref.")
    required = ["GITHUB_SHA", "GITHUB_REPOSITORY", "GITHUB_TOKEN", "COOLIFY_API_URL", "COOLIFY_API_TOKEN", "COOLIFY_APPLICATION_UUID", "COOLIFY_HEALTH_URL"]
    if any(not os.environ.get(name) for name in required):
        raise DeploymentError("Missing deployment configuration; set the documented GitHub secrets and Actions variable.")
    config = Config(os.environ["GITHUB_SHA"], os.environ["GITHUB_REPOSITORY"], os.environ["COOLIFY_APPLICATION_UUID"])
    if not SHA.fullmatch(config.sha) or not UUID.fullmatch(config.application_uuid) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", config.repository):
        raise DeploymentError("Invalid SHA, repository, or application UUID configuration.")
    coolify = JsonApi(os.environ["COOLIFY_API_URL"], os.environ["COOLIFY_API_TOKEN"])
    if not urlsplit(coolify.base_url).path.endswith("/api/v1"):
        raise DeploymentError("COOLIFY_API_URL must end with /api/v1.")
    github = JsonApi(os.environ.get("GITHUB_API_URL", "https://api.github.com"), os.environ["GITHUB_TOKEN"])
    # Public health uses a separate unauthenticated client. It must never
    # receive the Coolify or GitHub credential.
    health = JsonApi(os.environ["COOLIFY_HEALTH_URL"])
    if urlsplit(health.base_url).scheme != "https":
        raise DeploymentError("Public health verification requires HTTPS.")
    def interrupted(signum, frame):
        raise DeploymentInterrupted("Deployment workflow interrupted; its queued deployment will be cancelled when possible.")
    signal.signal(signal.SIGTERM, interrupted)
    deploy(config, coolify, lambda: current_main(github, config.repository), health)


if __name__ == "__main__":
    try:
        main()
    except (DeploymentError, KeyboardInterrupt) as error:
        print(f"::error::{error or 'Deployment interrupted.'}", file=sys.stderr)
        sys.exit(1)
