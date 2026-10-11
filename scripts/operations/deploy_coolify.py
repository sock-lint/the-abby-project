"""Deploy verified current main through Coolify without changing app configuration."""

import ipaddress
import json
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


SHA = re.compile(r"[0-9a-f]{40}")
UUID = re.compile(r"[A-Za-z0-9_-]+")


class DeploymentError(Exception):
    """An actionable failure whose message contains no API response or secret."""


class DeploymentInterrupted(DeploymentError):
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
        except (URLError, TimeoutError):
            raise DeploymentError("API request failed; check runner connectivity and API availability.") from None
        except (ValueError, UnicodeError):
            raise DeploymentError("API returned invalid JSON; check endpoint configuration.") from None


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


def active_deployment(coolify, config):
    history = coolify.request("GET", f"/deployments/applications/{config.application_uuid}?take=10")
    if not isinstance(history, dict) or not isinstance(history.get("deployments"), list):
        raise DeploymentError("Coolify returned invalid application deployment history.")
    # Prefer an already resolved exact commit over an unresolved native HEAD.
    # This application's history route provides ownership, not a name match.
    for commit in (config.sha, "HEAD"):
        for deployment in history["deployments"]:
            if (isinstance(deployment, dict) and deployment.get("status") in ("queued", "in_progress")
                    and deployment.get("commit") == commit and deployment.get("pull_request_id", 0) in (0, None)):
                uuid = deployment.get("deployment_uuid", "")
                if isinstance(uuid, str) and UUID.fullmatch(uuid):
                    return uuid
                raise DeploymentError("Coolify returned an invalid active deployment UUID.")
    return None


def deploy(config, coolify, latest_main, health, clock=time.monotonic, sleep=time.sleep):
    if latest_main() != config.sha:
        print("Skipping deployment: this workflow commit is no longer current main.", flush=True)
        return False
    check_application(coolify.request("GET", f"/applications/{config.application_uuid}"), config)
    deployment_uuid = active_deployment(coolify, config)
    # Recheck immediately before the only deployment mutation. Coolify 4.1.2's
    # API resolves HEAD itself and has no immutable commit input.
    if latest_main() != config.sha:
        print("Skipping deployment: main changed during application verification.", flush=True)
        return False
    if deployment_uuid is None:
        result = coolify.request("POST", "/deploy", {"uuid": config.application_uuid, "force": False})
        deployments = result.get("deployments", []) if isinstance(result, dict) else []
        if (not isinstance(deployments, list) or len(deployments) != 1
                or not isinstance(deployments[0], dict) or deployments[0].get("resource_uuid") != config.application_uuid):
            raise DeploymentError("Coolify did not return one deployment for the configured application; inspect its queue.")
        deployment_uuid = deployments[0].get("deployment_uuid", "")
    if not isinstance(deployment_uuid, str) or not UUID.fullmatch(deployment_uuid):
        raise DeploymentError("Coolify did not return a valid deployment UUID; inspect its queue.")
    print(f"Monitoring deployment {deployment_uuid} for commit {config.sha}.", flush=True)
    finished = False
    deadline = clock() + config.timeout
    previous_status = None
    checked_uuid = False
    try:
        while clock() < deadline:
            try:
                deployment = coolify.request("GET", f"/deployments/{deployment_uuid}")
            except ApiError as error:
                # Coolify 4.1.2's duplicate deploy response may name a newly
                # generated UUID instead of its existing queue row. Resolve
                # only an active deployment in this application's history.
                if error.status == 404 and not checked_uuid:
                    existing = active_deployment(coolify, config)
                    if existing and existing != deployment_uuid:
                        deployment_uuid = existing
                        checked_uuid = True
                        continue
                raise
            checked_uuid = True
            if (not isinstance(deployment, dict) or deployment.get("deployment_uuid") != deployment_uuid
                    or deployment.get("pull_request_id", 0) not in (0, None)):
                raise DeploymentError("Coolify returned a different or preview deployment.")
            status = deployment.get("status")
            commit = deployment.get("commit")
            finished = status in ("finished", "failed", "cancelled-by-user")
            if status != previous_status:
                if status not in ("queued", "in_progress", "finished", "failed", "cancelled-by-user"):
                    raise DeploymentError("Coolify returned an unknown deployment status; inspect this deployment.")
                print(f"Deployment status: {status}.", flush=True)
                previous_status = status
            if commit not in (None, "", "HEAD") and commit != config.sha:
                raise DeploymentError("Coolify resolved a different commit; this workflow will not accept that deployment.")
            if latest_main() != config.sha:
                raise DeploymentError("This deployment was superseded on main; a new workflow must deploy the latest commit.")
            if status == "finished":
                finished = True
                if commit != config.sha:
                    raise DeploymentError("Finished deployment did not prove the exact expected commit; inspect its resolved commit.")
                break
            if status in ("failed", "cancelled-by-user"):
                finished = True
                raise DeploymentError(f"Coolify deployment {status}; inspect this deployment in Coolify.")
            sleep(config.poll_interval)
        else:
            raise DeploymentError("Coolify deployment exceeded 20 minutes; inspect its queue and build status.")
    finally:
        if not finished:
            cancel_deployment(coolify, deployment_uuid)

    health_deadline = clock() + 120
    while clock() < health_deadline:
        try:
            result = health.request("GET")
            if isinstance(result, dict) and result.get("status") == "ok" and result.get("db") == "up":
                print(f"Coolify finished commit {config.sha}; public application and database are healthy.", flush=True)
                return True
        except DeploymentError:
            pass
        sleep(config.poll_interval)
    raise DeploymentError("Deployment finished, but public /health did not confirm application/database health within two minutes.")


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
