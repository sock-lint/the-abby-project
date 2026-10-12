using System;
using System.IO;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Reflection;
using AbbyCamp.Data;
using AbbyCamp.Services;
using AbbyCamp.Presentation;
using AbbyCamp.World;
using UnityEditor;
using UnityEngine;

namespace AbbyCamp.Editor
{
    /// <summary>Focused contract checks, also callable by Unity batch mode with
    /// -executeMethod AbbyCamp.Editor.ApiContractValidation.Run.</summary>
    public static class ApiContractValidation
    {
        private const string Habit = "{\"id\":9,\"name\":\"Read {a} book \\\"today\\\"\",\"habit_type\":\"positive\",\"user\":7,\"xp_reward\":5,\"max_taps_per_day\":1,\"taps_today\":0,\"strength\":-2,\"is_active\":true,\"pending_parent_review\":false,\"skill_tags\":[{\"skill\":2,\"skill_name\":\"Reading\",\"xp_weight\":1}]}";
        private static int checks;

        [MenuItem("Abby Camp/Validate API Contracts")]
        public static void Run()
        {
            checks = 0;
            ValidateSharedResponses();
            ValidateGreenlightFixtures();
            var user = ApiContract.ParseLogin("{\"id\":7,\"username\":\"abby\",\"display_name\":\"Abby\",\"role\":\"child\",\"token\":\"0123456789012345678901234567890123456789\"}", out var token);
            Check(user.id == 7 && user.DisplayName == "Abby" && token.Length == 40, "Flat Django login response");
            Reject(() => ApiContract.ParseLogin("{\"id\":7,\"username\":\"abby\",\"role\":\"child\",\"token\":\"bad\"}", out _), "Missing/invalid token");
            Reject(() => ApiContract.ParseUser("{\"username\":\"abby\",\"role\":\"child\"}"), "Missing identity");
            Reject(() => ApiContract.ParseUser("{\"id\":7,\"username\":\"abby\",\"role\":\"staff\"}"), "Unknown account role");
            var page = ApiContract.ParseHabitPage("{\"count\":21,\"next\":\"http://localhost:8000/api/habits/?page=2\",\"previous\":null,\"results\":[" + Habit + "]}");
            Check(page.count == 21 && page.results.Length == 1 && page.results[0].name == "Read {a} book \"today\"", "Paginated habits and escaped strings");
            var habit = page.results[0];
            Check(habit.IsEligibleForUser(7) && !habit.IsEligibleForUser(8), "Only own habits");
            habit.is_active = false;
            Check(!habit.IsEligibleForUser(7), "Inactive habits excluded");
            habit.is_active = true;
            habit.pending_parent_review = true;
            Check(!habit.IsEligibleForUser(7), "Unapproved habits excluded");
            habit.pending_parent_review = false;
            habit.habit_type = "negative";
            Check(!habit.IsEligibleForUser(7), "Negative-only habits excluded");
            habit.habit_type = "both";
            Check(habit.IsEligibleForUser(7), "Both-direction habits allow positive taps");
            habit.taps_today = habit.max_taps_per_day;
            Check(habit.DailyLimitReached, "Daily tap cap");
            Reject(() => ApiContract.ParseHabit(Habit.Replace(",\"pending_parent_review\":false", "")), "Missing approval cannot silently allow tapping");
            Reject(() => ApiContract.ParseHabit(Habit.Replace("\"is_active\":true", "\"is_active\":\"true\"")), "Safety flags must be booleans");
            Reject(() => ApiContract.ParseHabitPage("{\"count\":0,\"next\":null}"), "Missing results cannot masquerade as empty list");
            var empty = ApiContract.ParseHabitPage("{\"count\":0,\"next\":null,\"results\":[]}");
            Check(empty.results.Length == 0 && empty.next == null, "Empty final habit page");
            var tap = ApiContract.ParseHabitTap("{\"direction\":1,\"xp_reward\":5,\"new_strength\":0,\"game_event\":null}");
            Check(tap.direction == 1 && tap.new_strength == 0 && tap.game_event == null, "Confirmed tap remains valid without optional game event");
            var partialTap = ApiContract.ParseHabitTap("{\"direction\":1,\"xp_reward\":0,\"new_strength\":1,\"game_event\":{\"streak\":null,\"quest\":null,\"daily_challenge\":null,\"drops\":[],\"notifications\":[]}}");
            Check(partialTap.game_event != null && partialTap.game_event.streak == null && partialTap.game_event.quest == null && partialTap.game_event.daily_challenge == null, "Optional event nulls retain absent-event semantics");
            Reject(() => ApiContract.ParseHabitTap("{\"error\":\"No reward\",\"game_event\":{\"direction\":1,\"xp_reward\":5,\"new_strength\":2}}"), "Nested keys cannot fake a confirmed tap");
            Reject(() => ApiContract.ParseHabitTap("{\"direction\":-1,\"xp_reward\":0,\"new_strength\":2}"), "Positive-tap confirmation required");
            Reject(() => ApiContract.ParseHabitTap("{\"direction\":1,\"direction\":-1,\"xp_reward\":0,\"new_strength\":2}"), "Duplicate response keys rejected");
            Reject(() => ApiContract.ParseHabitTap("{\"direction\":1,\"xp_reward\":0,\"new_strength\":2}" + " trailing"), "Trailing response data rejected");
            var eventTap = ApiContract.ParseHabitTap("{\"direction\":1,\"xp_reward\":5,\"new_strength\":3,\"game_event\":{\"streak\":{\"is_first_today\":true,\"check_in_bonus_coins\":5,\"streak\":2},\"drops\":[{\"item_id\":4,\"item_name\":\"Fox egg\",\"quantity\":1,\"was_salvaged\":false}],\"quest\":{\"quest_name\":\"Forest trial\",\"completed\":true},\"daily_challenge\":{\"newly_completed\":true}}}");
            string withoutSkill = eventTap.DescribeConfirmedOutcome(new HabitDto());
            Check(withoutSkill == "Ritual recorded. Strength: 3." && eventTap.game_event.drops[0].item_name == "Fox egg", "Confirmation omits unverified event rewards while retaining event data");
            Check(eventTap.DescribeConfirmedOutcome(ApiContract.ParseHabit(Habit)) == "Ritual recorded. Strength: 3." && tap.DescribeConfirmedOutcome() == "Ritual recorded. Strength: 0.", "Configured XP and null game event do not change confirmed base outcome");
            var definite = ApiContract.HttpError(400, "{\"error\":\"Daily limit reached\"}", true, false);
            Check(!definite.OutcomeUnknown && definite.Message == "Daily limit reached", "Validation rejection is definite");
            Check(ApiContract.HttpError(503, "<html>down</html>", true, false).OutcomeUnknown, "Server error after POST may have committed");
            Check(ApiContract.HttpError(408, "", true, false).OutcomeUnknown, "HTTP timeout after POST may have committed");
            Check(ApiContract.HttpError(0, "", true, true).OutcomeUnknown, "Lost POST response may have committed");
            Check(!ApiContract.HttpError(0, "", false, true).OutcomeUnknown, "Failed reads are not failed mutations");
            Check(ApiContract.HttpError(401, "{\"detail\":\"Invalid token.\"}", false, false).RequiresLogin, "Expired token ends session");
            Check(AbbyApiClient.TryValidateBaseUrl("http://127.0.0.1:8000/", out var origin, out _) && origin == "http://127.0.0.1:8000", "Loopback HTTP origin normalized");
            Check(AbbyApiClient.TryValidateBaseUrl("http://localhost:8000", out _, out _), "Localhost HTTP allowed");
            Check(AbbyApiClient.TryValidateBaseUrl("https://abby.example.com", out _, out _), "Remote HTTPS allowed");
            Check(!AbbyApiClient.TryValidateBaseUrl("http://192.168.1.2:8000", out _, out _), "Remote HTTP prohibited");
            Check(!AbbyApiClient.TryValidateBaseUrl("https://abby.example.com/api/", out _, out _), "Origin must not include an endpoint path");
            Check(!AbbyApiClient.TryValidateBaseUrl("https://user:pass@abby.example.com", out _, out _), "Embedded credentials rejected");
            Check(AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "/api/habits/?page=2", out _), "Same-origin pagination supported");
            Check(!AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "https://other.example.com/api/habits/?page=2", out _), "Pagination cannot exfiltrate token to another host");
            Check(!AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "http://abby.example.com/api/habits/?page=2", out _), "Pagination cannot downgrade HTTPS");
            Check(!AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "/api/auth/", out _), "Pagination restricted to habit endpoint");

            const string bloom = "{\"receipt_id\":\"journal:123\",\"type\":\"memory_bloom\",\"title\":\"Memory bloom\",\"earned_at\":\"2026-10-10T12:34:56Z\"}";
            const string meadowJson = "{\"schema_version\":1,\"keepsake_count\":1,\"journal_xp_awarded\":5,\"keepsakes\":[" + bloom + "]}";
            var meadow = ApiContract.ParseMeadow(meadowJson);
            Check(meadow.keepsake_count == 1 && meadow.keepsakes[0].receipt_id == "journal:123", "Read-only meadow receipt metadata");
            var emptyMeadow = ApiContract.ParseMeadow("{\"schema_version\":1,\"keepsake_count\":0,\"journal_xp_awarded\":0,\"keepsakes\":[]}");
            Check(emptyMeadow.keepsakes.Length == 0, "Empty collection remains a valid acknowledged read");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("\"schema_version\":1", "\"schema_version\":2")), "Unknown meadow schema cannot be displayed as progress");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("\"keepsake_count\":1", "\"keepsake_count\":0")), "Collection count cannot be smaller than its window");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("journal:123", "journal:invalid")), "Keepsake requires stable journal receipt identity");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("memory_bloom", "unverified_reward")), "Unknown reward type is not recognised as an earned bloom");
            Reject(() => ApiContract.ParseMeadow(meadowJson.Replace("2026-10-10T12:34:56Z", "not-a-date")), "Keepsake requires an earned date");
            Reject(() => ApiContract.ParseMeadow("{\"schema_version\":1,\"keepsake_count\":2,\"journal_xp_awarded\":10,\"keepsakes\":[" + bloom + "," + bloom + "]}"), "Duplicate keepsake receipts rejected");
            var localMemory = new Dictionary<string, string>();
            string Read(string key) => localMemory.TryGetValue(key, out var value) ? value : "";
            void Remember(string key, string value) => localMemory[key] = value;
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 7, meadow, Read, Remember) == null, "First visit baselines existing awarded history without replaying a celebration");
            var nextMeadow = ApiContract.ParseMeadow(meadowJson.Replace("journal:123", "journal:124").Replace("12:34:56Z", "12:35:56Z"));
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 7, nextMeadow, Read, Remember)?.receipt_id == "journal:124", "New acknowledged receipt celebrates locally");
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 7, nextMeadow, Read, Remember) == null, "Refresh cannot replay receipt celebration");
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 7, emptyMeadow, Read, Remember) == null
                && MeadowReceiptMemory.Observe("https://abby.example.com", 7, meadow, Read, Remember) == null, "Deletion and older window items cannot replay historical celebrations");
            Check(MeadowReceiptMemory.Observe("https://abby.example.com", 8, nextMeadow, Read, Remember) == null, "Receipt presentation baselines separately for another child");
            Check(MeadowReceiptMemory.Observe("https://other.example.com", 7, nextMeadow, Read, Remember) == null, "Receipt presentation stays scoped to its server origin");

            ValidatePlayHomeContracts();
            ValidateCompanionCareContracts();
            ValidateOwnedCreaturePresentation();
            ValidateHatchingContracts();
            ValidateExpeditionContracts();
            ValidateBreedingContracts();
            ValidateCareRefreshLock();
            var gameObject = new GameObject("API validation client");
            try
            {
                var client = gameObject.AddComponent<AbbyApiClient>();
                string readUrl = client.BuildReadUrl("https://abby.example.com/api/auth/me/");
                string readNamespace = new Uri(readUrl).Query.Substring("?_abby_session=".Length);
                Check(Guid.TryParseExact(readNamespace, "N", out _), "Private reads use a random noncredential namespace");
                Check(client.BuildReadUrl("https://abby.example.com/api/character/").EndsWith("?_abby_session=" + readNamespace),
                    "Private reads share one namespace within a session");
                string pageUrl = client.BuildReadUrl("https://abby.example.com/api/habits/?page=2&name=a%26b&_abby_session=old&%5Fabby_session=older&_abby_session");
                Check(new Uri(pageUrl).Query == "?page=2&name=a%26b&_abby_session=" + readNamespace,
                    "Pagination preserves filters and replaces all inherited session keys");
                client.ClearSession();
                string nextSessionUrl = client.BuildReadUrl("https://abby.example.com/api/auth/me/");
                Check(nextSessionUrl != readUrl && Guid.TryParseExact(new Uri(nextSessionUrl).Query.Substring("?_abby_session=".Length), "N", out _),
                    "Logout or account replacement rotates the read namespace");
                var otherClient = gameObject.AddComponent<AbbyApiClient>();
                Check(otherClient.BuildReadUrl("https://abby.example.com/api/auth/me/") != nextSessionUrl,
                    "New clients cannot reuse a previous page's private read cache");
                ApiError rejection = null;
                bool completed = false;
                var coroutine = client.LogPositiveHabit(null, _ => completed = true, problem => rejection = problem);
                Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin, "Logged-out tap never issues a request");
                rejection = null;
                coroutine = client.ResumeBrowserSession(_ => completed = true, problem => rejection = problem);
                Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin && !client.IsAuthenticated,
                    "Missing browser credential cannot mint a token or authorize camp actions");
                rejection = null;
                coroutine = client.MarkNotificationRead(1, _ => completed = true, problem => rejection = problem);
                Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin,
                    "Logged-out notification acknowledgement never issues a request");
                rejection = null;
                coroutine = client.FetchNotifications(_ => completed = true, problem => rejection = problem, "https://outside.example.com/api/notifications/?page=2");
                Check(!coroutine.MoveNext() && !completed && rejection != null,
                    "Unsafe inbox continuation is rejected before a request starts");
                foreach (var action in new Func<Action<ApiError>, System.Collections.IEnumerator>[]
                {
                    fail => client.FeedPet(51, 71, _ => completed = true, fail),
                    fail => client.ActivatePet(52, _ => completed = true, fail),
                    fail => client.ActivateMount(62, _ => completed = true, fail),
                    fail => client.HatchPet(73, 75, _ => completed = true, fail),
                    fail => client.BreedMounts(61, 62, _ => completed = true, fail),
                    fail => client.StartExpedition(61, "short", _ => completed = true, fail),
                    fail => client.ClaimExpedition(103, _ => completed = true, fail),
                })
                {
                    rejection = null;
                    coroutine = action(problem => rejection = problem);
                    Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin,
                        "Logged-out creature care never issues a mutation");
                }
                rejection = null;
                coroutine = client.FetchExpeditions(_ => completed = true, problem => rejection = problem);
                Check(!coroutine.MoveNext() && !completed && rejection != null && rejection.RequiresLogin,
                    "Logged-out expedition history never issues a request");
                client.ConfigureBaseUrl("https://abby.example.com", out _);
                Check(!client.ConfigureBaseUrl("http://remote.example.com", out _) && client.BaseUrl == "https://abby.example.com", "Rejected configuration preserves valid origin");
            }
            finally { UnityEngine.Object.DestroyImmediate(gameObject); }
            Debug.Log("Abby Camp API contracts: " + checks + " checks passed.");
        }

        private static void ValidateSharedResponses()
        {
            // These are the same raw Django response bodies used by the backend
            // drift checks and React API tests. Keep them outside Assets so the
            // synthetic account/token data cannot ship in a player build.
            var login = ApiContract.ParseLogin(ReadFixture("auth-login-child.json"), out var token);
            Check(login.id == 7 && login.username == "fixture-child" && login.role == "child"
                && login.DisplayName == "Fixture Child" && token == "0123456789012345678901234567890123456789",
                "Shared Django login response preserves account identity and synthetic token");
            Check(login.family != null && login.family.id == 1 && login.family.timezone == "America/Phoenix",
                "Shared Django login includes the account's family");

            var user = ApiContract.ParseUser(ReadFixture("auth-me-child.json"));
            Check(user.id == login.id && user.username == login.username && user.role == login.role
                && user.family != null && user.family.id == login.family.id,
                "Shared browser session response matches the authenticated account");

            var page = ApiContract.ParseHabitPage(ReadFixture("habits-page-1.json"));
            Check(page.count == 21 && page.results.Length == 20
                && page.next == "http://testserver/api/habits/?page=2",
                "Shared Django habits response retains real pagination");
            var habit = page.results[0];
            Check(habit.id == 9 && habit.name == "Read {a} book \"today\"" && habit.strength == -2
                && habit.taps_today == 0 && habit.IsEligibleForUser(user.id) && !habit.IsEligibleForUser(user.id + 1),
                "Shared habit preserves escaped text, strength, and account eligibility");
            Check(habit.skill_tags.Length == 1 && habit.skill_tags[0].skill == 2
                && habit.skill_tags[0].skill_name == "Reading" && habit.skill_tags[0].xp_weight == 1,
                "Shared habit skill tags survive Unity DTO parsing");
            Check(!page.results[1].IsEligibleForUser(user.id) && page.results[2].IsEligibleForUser(user.id)
                && !page.results[3].IsEligibleForUser(user.id),
                "Shared negative, both-direction, and inactive habits preserve eligibility");

            var lastPage = ApiContract.ParseHabitPage(ReadFixture("habits-page-2.json"));
            Check(lastPage.count == page.count && lastPage.results.Length == 1
                && lastPage.results[0].id == 29 && lastPage.next == null,
                "Shared final habit page preserves the explicit null continuation");
            var emptyPage = ApiContract.ParseHabitPage(ReadFixture("habits-empty.json"));
            Check(emptyPage.count == 0 && emptyPage.results.Length == 0 && emptyPage.next == null,
                "Shared empty habit response remains an empty final page");

            var tap = ApiContract.ParseHabitTap(ReadFixture("habit-positive-tap.json"));
            Check(tap.direction == 1 && tap.xp_reward == 5 && tap.new_strength == -1
                && tap.DescribeConfirmedOutcome(habit) == "Ritual recorded. Strength: -1.",
                "Shared committed tap confirms strength without inventing granted rewards");
            Check(tap.game_event != null && tap.game_event.trigger_type == "habit_log"
                && tap.game_event.streak != null && tap.game_event.streak.streak == 1
                && tap.game_event.drops.Length == 0 && tap.game_event.quest == null
                && tap.game_event.daily_challenge != null && tap.game_event.daily_challenge.progress == 1,
                "Shared real game-loop response preserves nested events and null quest");

            var noEvent = ApiContract.ParseHabitTap(ReadFixture("habit-positive-tap-no-event.json"));
            Check(noEvent.direction == 1 && noEvent.new_strength == -1 && noEvent.game_event == null
                && noEvent.DescribeConfirmedOutcome(habit) == "Ritual recorded. Strength: -1.",
                "Shared committed tap remains confirmed without an optional game event");
            var limit = ApiContract.HttpError(400, ReadFixture("habit-positive-tap-limit.json"), true, false);
            Check(limit.StatusCode == 400 && !limit.OutcomeUnknown
                && limit.Message == "Daily limit reached (1 taps/day).",
                "Shared Django daily-limit response is a definite rejection");
        }

        private static string ReadFixture(string name)
        {
            var path = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", "..", "contracts", "api", "fixtures", name));
            if (!File.Exists(path))
                throw new FileNotFoundException("Shared API fixture missing. Validate Unity from a full repository checkout: " + name, path);
            return File.ReadAllText(path);
        }

        // Payment actions remain in the parent web app. These Editor-only
        // projections validate the shared response contract without adding a
        // second payout client or shipping synthetic banking data in a player.
        [Serializable] private sealed class GreenlightSnapshotFixture
        {
            public int id;
            public int user;
            public string amount;
            public string as_of;
            public int created_by;
        }

        [Serializable] private sealed class GreenlightPayoutFixture
        {
            public int id;
            public string amount;
            public string transferred_on;
            public string source;
            public bool reconciled;
        }

        [Serializable] private sealed class GreenlightOverviewFixture
        {
            public int user_id;
            public string owed_balance;
            public string approved_payable;
            public string pending_hourly;
            public GreenlightSnapshotFixture balance_snapshot;
            public GreenlightPayoutFixture[] payouts;
        }

        [Serializable] private sealed class GreenlightPayoutResponseFixture
        {
            public bool created;
            public GreenlightPayoutFixture payout;
        }

        [Serializable] private sealed class GreenlightPreviewRowFixture
        {
            public string fingerprint;
            public string amount;
            public bool eligible;
            public int[] match_candidates;
        }

        [Serializable] private sealed class GreenlightPreviewFixture
        {
            public GreenlightPreviewRowFixture[] rows;
            public string[] schema;
        }

        [Serializable] private sealed class GreenlightReconcileFixture
        {
            public int recorded;
            public int matched;
            public int duplicates;
        }

        private static void ValidateGreenlightFixtures()
        {
            string missingJson = ReadFixture("greenlight-overview-no-snapshot.json");
            var missing = JsonUtility.FromJson<GreenlightOverviewFixture>(missingJson);
            Check(missing.user_id == 7 && missing.owed_balance == "25.00"
                && missing.approved_payable == "20.00" && missing.pending_hourly == "5.00",
                "Shared payout overview separates approved money from pending hourly earnings");
            Check(Regex.IsMatch(missingJson, "\"balance_snapshot\"\\s*:\\s*null") && missing.payouts.Length == 0,
                "An unknown Greenlight balance is explicit null, not a fabricated zero");
            foreach (string field in new[] { "owed_balance", "approved_payable", "pending_hourly" })
                Check(HasQuotedMoney(missingJson, field), "Shared payout amount retains exact decimal-string cents: " + field);

            string snapshotJson = ReadFixture("greenlight-balance-snapshot.json");
            var snapshot = JsonUtility.FromJson<GreenlightSnapshotFixture>(snapshotJson);
            Check(snapshot.user == 7 && snapshot.created_by == 6 && snapshot.amount == "40.25"
                && HasQuotedMoney(snapshotJson, "amount")
                && DateTimeOffset.TryParse(snapshot.as_of, CultureInfo.InvariantCulture, DateTimeStyles.None, out var asOf)
                && asOf.ToUniversalTime() == new DateTimeOffset(2026, 10, 11, 18, 0, 0, TimeSpan.Zero),
                "Reported Greenlight balance retains a parent, exact amount and actual as-of timestamp");
            var known = JsonUtility.FromJson<GreenlightOverviewFixture>(ReadFixture("greenlight-overview.json"));
            Check(known.balance_snapshot != null && known.balance_snapshot.id == snapshot.id
                && known.balance_snapshot.amount == snapshot.amount && known.owed_balance == missing.owed_balance,
                "Recording Greenlight's reported balance does not change what the parent owes");

            string payoutJson = ReadFixture("greenlight-payout.json");
            var payout = JsonUtility.FromJson<GreenlightPayoutResponseFixture>(payoutJson);
            Check(payout.created && payout.payout.amount == "12.50" && HasQuotedMoney(payoutJson, "amount")
                && payout.payout.source == "manual" && !payout.payout.reconciled
                && payout.payout.transferred_on == "2026-10-11",
                "Parent-confirmed payout retains amount, transfer date and unreconciled manual source");
            var preview = JsonUtility.FromJson<GreenlightPreviewFixture>(ReadFixture("greenlight-preview.json"));
            Check(preview.schema.Length == 5 && preview.rows.Length == 3 && preview.rows[0].eligible
                && preview.rows[0].match_candidates.Length == 1 && preview.rows[0].match_candidates[0] == payout.payout.id
                && preview.rows[1].eligible && preview.rows[1].amount == "7.50"
                && !preview.rows[2].eligible && preview.rows[2].amount == "-3.00",
                "Statement preview can match a paid transfer without treating card spending as money owed");
            Check(preview.rows[0].fingerprint.Length == 64 && preview.rows[1].fingerprint.Length == 64
                && preview.rows[0].fingerprint != preview.rows[1].fingerprint,
                "Statement transfers preserve stable distinct reconciliation identities");
            var reconciled = JsonUtility.FromJson<GreenlightReconcileFixture>(ReadFixture("greenlight-reconcile.json"));
            Check(reconciled.recorded == 1 && reconciled.matched == 1 && reconciled.duplicates == 0,
                "Reconciliation records one new payout and matches the existing payout once");
            var final = JsonUtility.FromJson<GreenlightOverviewFixture>(ReadFixture("greenlight-overview-reconciled.json"));
            Check(final.owed_balance == "5.00" && final.approved_payable == "0.00" && final.pending_hourly == "5.00"
                && final.balance_snapshot.amount == snapshot.amount && final.balance_snapshot.as_of == snapshot.as_of
                && final.payouts.Length == 2 && final.payouts[0].reconciled && final.payouts[1].reconciled,
                "Confirmed payouts reduce money owed while the separately reported Greenlight balance stays as-of its observation");
        }

        private static bool HasQuotedMoney(string json, string field)
        {
            return Regex.IsMatch(json, "\"" + Regex.Escape(field) + "\"\\s*:\\s*\"-?[0-9]+\\.[0-9]{2}\"");
        }

        private static void ValidatePlayHomeContracts()
        {
            const string date = "2026-10-10T12:34:56Z";
            const string transaction = "{\"id\":12,\"user\":7,\"amount\":-5,\"reason\":\"redemption\",\"description\":\"Reward shelf\",\"created_at\":\"" + date + "\"}";
            const string coinsJson = "{\"balance\":120,\"breakdown\":{\"redemption\":-5},\"recent_transactions\":[" + transaction + "]}";
            var coins = ApiContract.ParseCoins(coinsJson, 7);
            Check(coins.balance == 120 && coins.recent_transactions[0].amount == -5, "Authoritative coin history retains signed spending amounts");
            Check(ApiContract.ParseCoins("{\"balance\":0,\"recent_transactions\":[]}", 7).recent_transactions.Length == 0, "An empty coin ledger is valid");
            Reject(() => ApiContract.ParseCoins(coinsJson, 8), "Another account's coin ledger is rejected");
            Reject(() => ApiContract.ParseCoins(coinsJson.Replace("\"amount\":-5,", ""), 7), "Missing transaction amounts cannot default into rewards");
            Reject(() => ApiContract.ParseCoins("{\"balance\":120,\"recent_transactions\":[" + transaction + "," + transaction + "]}", 7), "Duplicate ledger records are rejected");
            const string drop = "{\"id\":4,\"item\":3,\"item_name\":\"Fox egg\",\"item_icon\":\"egg\",\"item_sprite_key\":\"fox-egg\",\"item_rarity\":\"rare\",\"trigger_type\":\"homework_approved\",\"quantity\":2,\"was_salvaged\":true,\"created_at\":\"" + date + "\"}";
            var drops = ApiContract.ParseRecentDrops("[" + drop + "]");
            Check(drops[0].id == 4 && drops[0].quantity == 2 && drops[0].was_salvaged, "Committed drops retain identity, quantity and salvage state");
            Check(ApiContract.ParseRecentDrops("[]").Length == 0, "No drops is a valid history");
            Reject(() => ApiContract.ParseRecentDrops("[" + drop + "," + drop + "]"), "Duplicate drop IDs cannot be announced twice");
            Reject(() => ApiContract.ParseRecentDrops("[" + drop.Replace("\"was_salvaged\":true", "\"was_salvaged\":\"true\"") + "]"), "Salvage state requires an explicit boolean");
            Reject(() => ApiContract.ParseRecentDrops("[" + drop.Replace("\"quantity\":2", "\"quantity\":0") + "]"), "Drop quantities must be positive");
            Reject(() => ApiContract.ParseRecentDrops("[" + new string(' ', 2 * 1024 * 1024) + "]"), "Oversized bare-array responses are bounded");

            const string notification = "{\"id\":20,\"title\":\"New drop\",\"message\":\"An egg is waiting\",\"notification_type\":\"drop_received\",\"is_read\":false,\"created_at\":\"" + date + "\",\"link\":\"/inventory\"}";
            var page = ApiContract.ParseNotificationPage("{\"count\":21,\"next\":\"https://abby.example.com/api/notifications/?page=2\",\"results\":[" + notification + "]}");
            Check(page.count == 21 && !page.results[0].is_read && page.next.EndsWith("page=2"), "Inbox parsing preserves unread state and pagination");
            Check(ApiContract.ParseNotificationPage("{\"count\":0,\"next\":null,\"results\":[]}").next == null, "An empty inbox uses a true null continuation");
            Check(ApiContract.ParseUnreadCount("{\"count\":35}").count == 35, "Global unread count is independent of the latest page");
            Reject(() => ApiContract.ParseNotification(notification.Replace(",\"is_read\":false", "")), "Missing read state cannot silently acknowledge a notification");
            Reject(() => ApiContract.ParseNotification(notification.Replace(date, "invalid")), "Notification dates are validated");
            Reject(() => ApiContract.ParseUnreadCount("{\"count\":-1}"), "Unread counts cannot be negative");
            Reject(() => ApiContract.ParseNotificationPage("{\"count\":2,\"next\":null,\"results\":[" + notification + "," + notification + "]}"), "Duplicate inbox rows are rejected");
            Reject(() => ApiContract.ParseNotificationPage("{\"count\":0,\"next\":\"?page=2\",\"results\":[]}"), "An empty page cannot authorize a continuation loop");
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?page=2", out var next) && next == "https://abby.example.com/api/notifications/?page=2", "Inbox page URLs stay at the same-origin endpoint");
            const string readNamespace = "0123456789abcdef0123456789abcdef";
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?_abby_session=" + readNamespace + "&page=2", out next)
                && next == "https://abby.example.com/api/notifications/?page=2",
                "Django inbox continuation strips the inherited private read namespace");
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?page=2&_abby_session=" + readNamespace, out next)
                && next == "https://abby.example.com/api/notifications/?page=2",
                "Inbox continuation accepts the namespace after its page number");
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?_abby_session=" + readNamespace, out next)
                && next == "https://abby.example.com/api/notifications/",
                "Namespace-only inbox reads resolve to the first page");
            Check(AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?page=2&%5Fabby_session=" + readNamespace, out next)
                && next == "https://abby.example.com/api/notifications/?page=2",
                "URI-normalized private namespace keys are still stripped from inbox continuations");
            Check(AbbyApiClient.TryResolveHabitPageUrl("https://abby.example.com", "/api/habits/?_abby_session=" + readNamespace + "&page=2", out var habitNext)
                && habitNext == "https://abby.example.com/api/habits/?_abby_session=" + readNamespace + "&page=2",
                "Habit continuation retains the inherited namespace for replacement by Send");
            foreach (string unsafeQuery in new[] { "page=2&_abby_session=invalid", "page=2&_abby_session=" + readNamespace + "&token=x", "page=2&page=3&_abby_session=" + readNamespace,
                "page=2&_abby_session=" + readNamespace + "&_abby_session=" + readNamespace, "page=2&%5Fabby_session_extra=" + readNamespace })
                Check(!AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", "/api/notifications/?" + unsafeQuery, out _),
                    "Private namespaces cannot weaken inbox query validation: " + unsafeQuery);
            foreach (string unsafePage in new[] { "https://other.example.com/api/notifications/?page=2", "http://abby.example.com/api/notifications/?page=2", "/api/auth/", "/api/notifications/?page=0", "/api/notifications/?page=501", "/api/notifications/?page=2&token=x", "/api/notifications/?page=2#secret", "https://user@abby.example.com/api/notifications/?page=2" })
                Check(!AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", unsafePage, out _), "Unsafe inbox page rejected: " + unsafePage);

            var sharedInbox = ApiContract.ParseNotificationPage(ReadFixture("notifications-page-1.json"));
            var sharedInboxLast = ApiContract.ParseNotificationPage(ReadFixture("notifications-page-2.json"));
            Check(sharedInbox.count == 21 && sharedInbox.results.Length == 20 && sharedInboxLast.results.Length == 1,
                "Shared inbox fixtures preserve both real notification pages");
            Check(sharedInbox.next.StartsWith("/api/notifications/", StringComparison.Ordinal)
                && AbbyApiClient.TryResolveNotificationPageUrl("https://abby.example.com", sharedInbox.next, out next)
                && next == "https://abby.example.com/api/notifications/?page=2",
                "Relative Django continuations retain the browser's HTTPS origin across HTTP proxy hops");
            for (int index = 0; index < sharedInbox.results.Length; index++)
                Check(sharedInbox.results[index].id == 101 + index && !sharedInbox.results[index].is_read,
                    "Reading a shared inbox page preserves each unread notification's identity");
            Check(sharedInboxLast.results[0].id == 121 && !sharedInboxLast.results[0].is_read && sharedInboxLast.next == null,
                "The final shared inbox page ends pagination without acknowledging updates");
            var sharedInboxEmpty = ApiContract.ParseNotificationPage(ReadFixture("notifications-empty.json"));
            Check(sharedInboxEmpty.count == 0 && sharedInboxEmpty.results.Length == 0 && sharedInboxEmpty.next == null,
                "An empty shared inbox preserves the real pagination envelope");

            const string species = "{\"id\":1,\"name\":\"Fox\",\"icon\":\"fox\",\"sprite_key\":\"fox\",\"description\":\"Friendly\",\"food_preference\":\"fruit\"}";
            const string potion = "{\"id\":2,\"slug\":null,\"name\":\"Mint\",\"sprite_key\":\"mint\",\"color_hex\":\"#AABBCC\",\"rarity\":\"common\",\"description\":\"Soft green\"}";
            const string pet = "{\"id\":8,\"species\":" + species + ",\"potion\":" + potion + ",\"name\":\"Clover\",\"growth_points\":12,\"is_active\":true,\"evolved_to_mount\":false,\"is_fully_grown\":false,\"happiness_level\":\"happy\",\"last_fed_at\":null,\"created_at\":\"" + date + "\",\"updated_at\":\"" + date + "\"}";
            const string mount = "{\"id\":5,\"species\":" + species + ",\"potion\":" + potion + ",\"is_active\":true,\"last_bred_at\":null,\"can_breed\":true,\"breeding_cooldown_seconds\":0,\"active_expedition\":null,\"created_at\":\"" + date + "\",\"updated_at\":\"" + date + "\"}";
            const string stableJson = "{\"pets\":[" + pet + "],\"mounts\":[" + mount + "],\"total_pets\":1,\"total_mounts\":1,\"total_possible\":2}";
            var stable = ApiContract.ParseStable(stableJson);
            Check(stable.ActiveCompanion?.DisplayName == "Clover" && stable.ActiveMount?.DisplayName == "Mint Fox", "Stable reflects genuinely owned active creatures");
            Check(stable.pets[0].last_fed_at == null && stable.mounts[0].last_bred_at == null, "Nullable care dates do not become fabricated timestamps");
            Check(ApiContract.ParseStable("{\"pets\":[],\"mounts\":[],\"total_pets\":0,\"total_mounts\":0,\"total_possible\":0}").ActiveCompanion == null, "Empty ownership does not invent a starter companion");
            Check(ApiContract.ParseStable(stableJson.Replace("\"evolved_to_mount\":false", "\"evolved_to_mount\":true")).ActiveCompanion == null, "Evolved pets do not masquerade as the active companion");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"total_pets\":1", "\"total_pets\":0")), "Stable ownership counts must agree with its arrays");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"growth_points\":12", "\"growth_points\":101")), "Out-of-range companion growth is rejected");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"is_fully_grown\":false", "\"is_fully_grown\":true")), "Growth status cannot be fabricated by missing or inconsistent state");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"color_hex\":\"#AABBCC\"", "\"color_hex\":\"invalid\"")), "Potion colors cannot be untrusted markup");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"species\":" + species, "\"species\":null")), "Owned creature species are required");

            Check(AbbyApiClient.DestinationPath((PlayDestination)999) == null, "Unknown typed destinations cannot navigate");
            Check(AbbyApiClient.TryResolveNotificationDestination("/inventory", "drop_received", out var destination) && destination == PlayDestination.Satchel, "Legacy inventory links resolve to Satchel");
            Check(AbbyApiClient.TryResolveNotificationDestination("/projects/123", "project_approved", out destination) && destination == PlayDestination.TasksVentures, "Legacy project detail links resolve to its task tab");
            Check(AbbyApiClient.TryResolveNotificationDestination("/chronicle?tab=grades", "journal_reply", out destination) && destination == PlayDestination.Grades, "Safe notification link retains the appropriate memoir tab");
            Check(AbbyApiClient.TryResolveNotificationDestination("/unknown", "print_finished", out destination) && destination == PlayDestination.TasksForge, "Known notification types supply a typed fallback");
            Check(AbbyApiClient.TryResolveNotificationDestination("https://outside.example.com/", "journal_reply", out destination) && destination == PlayDestination.Journal, "Unsafe links can only fall back to a known typed destination");
            foreach (string unsafeLink in new[] { "https://outside.example.com/", "//outside.example.com/", "/\\outside.example.com/", "/chronicle?tab=journal&token=secret", "/%2foutside.example.com/", "/bestiary#secret", "/unknown" })
                Check(!AbbyApiClient.TryResolveNotificationDestination(unsafeLink, "unknown_type", out _), "Raw or unknown notification destinations are never followed: " + unsafeLink);
        }

        private static void ValidateOwnedCreaturePresentation()
        {
            var species = new SpeciesDto { id = 71, name = "Chick", sprite_key = "cute-chick" };
            var potion = new PotionDto { id = 72, slug = "base", name = "Base" };
            var pet = new OwnedPetDto { id = 73, species = species, potion = potion, name = "Peep", is_active = true, growth_points = 75 };
            var mount = new OwnedMountDto { id = 74, species = species, potion = potion, is_active = true };
            var stable = new StableDto { pets = new[] { pet }, mounts = new[] { mount } };
            var selected = OwnedCompanionResolver.Resolve(stable);
            Check(selected.Kind == OwnedCompanionKind.Pet && selected.CreatureId == pet.id && !selected.IsEvolved,
                "Owned presentation defaults to the saved active companion without activating a mount");
            Check(OwnedCompanionResolver.Resolve(stable, OwnedCompanionKind.Mount, mount.id).CreatureId == mount.id,
                "An acknowledged active mount choice takes precedence over an independent active pet flag");
            Check(OwnedCompanionResolver.Resolve(stable, OwnedCompanionKind.Mount, 999).CreatureId == pet.id,
                "A stale or foreign presentation preference cannot invent an owned mount");
            mount.is_active = false;
            Check(OwnedCompanionResolver.Resolve(stable, OwnedCompanionKind.Mount, mount.id).CreatureId == pet.id,
                "A preference loses precedence when its saved row is no longer active");
            pet.growth_points = 100;
            Check(!OwnedCompanionResolver.Resolve(stable).IsEvolved,
                "Full growth alone cannot invent confirmed evolution");
            pet.evolved_to_mount = true;
            Check(OwnedCompanionResolver.Resolve(stable).IsEvolved && OwnedCompanionResolver.Resolve(stable).CreatureId == pet.id,
                "The retained active evolved pet displays its grown form without selecting a mount");
            Check(selected.WithConfirmedFeed(pet.id, new PetFeedDto { new_growth = 100, evolved = true, mount_id = mount.id }).IsEvolved,
                "A confirmed feed receipt can immediately present evolution of the displayed companion");
            Check(!selected.WithConfirmedFeed(999, new PetFeedDto { new_growth = 100, evolved = true, mount_id = mount.id }).IsEvolved,
                "Another pet's feed receipt cannot change the displayed companion");
            Check(OwnedCompanionResolver.Resolve(null).Kind == OwnedCompanionKind.None
                && OwnedCompanionResolver.Resolve(new StableDto { pets = Array.Empty<OwnedPetDto>(), mounts = Array.Empty<OwnedMountDto>() }).Kind == OwnedCompanionKind.None,
                "Cleared and empty account collections carry no creature presentation ownership");

            var world = ScriptableObject.CreateInstance<CampPresentationDefinition>();
            var chick = ScriptableObject.CreateInstance<VisualDefinition>();
            var bird = ScriptableObject.CreateInstance<VisualDefinition>();
            var chickModel = new GameObject("Synthetic Chick model");
            var birdModel = new GameObject("Synthetic Bird model");
            var actor = new GameObject("Synthetic owned companion");
            try
            {
                chick.ModelPrefab = chickModel; bird.ModelPrefab = birdModel;
                world.OwnedCreatureAppearances = new[] { new OwnedCreatureVisualBinding
                    { SpeciesSpriteKey = "cute-chick", PotionSlug = "base", Companion = chick, Evolved = bird } };
                Check(world.TryResolveOwnedAppearance("cute-chick", "base", false, out var resolved) && resolved == chick,
                    "The explicitly bound Base Chick resolves to its own model");
                Check(world.TryResolveOwnedAppearance("cute-chick", "base", true, out resolved) && resolved == bird,
                    "The explicitly bound evolved Chick resolves to Bird");
                Check(!world.TryResolveOwnedAppearance("wolf", "base", false, out _)
                    && !world.TryResolveOwnedAppearance("cute-chick", "fire", false, out _),
                    "Unrelated species and unprepared potion variants cannot inherit Chick artwork");
                bird.ModelPrefab = null;
                Check(!world.TryResolveOwnedAppearance("cute-chick", "base", true, out _),
                    "Missing licensed models remain an explicit preview instead of claimed owned artwork");
                bird.ModelPrefab = birdModel;
                var follower = actor.AddComponent<CompanionFollower>();
                follower.Configure(chick, bird);
                follower.SetOwnedAppearance(chick);
                var modelId = actor.transform.Find("Appearance").gameObject.GetEntityId();
                follower.SetOwnedAppearance(chick);
                follower.ToggleAppearance();
                Check(follower.HasOwnedAppearance && follower.Appearance.Definition == chick
                    && actor.transform.Find("Appearance").gameObject.GetEntityId() == modelId,
                    "HUD refreshes and the development swap key preserve the selected model instance");
                follower.SetOwnedAppearance(bird);
                Check(follower.Appearance.Definition == bird && follower.HasOwnedAppearance,
                    "Confirmed model replacement retains the stationary actor root");
                follower.ClearOwnedAppearance(true);
                Check(!follower.HasOwnedAppearance && follower.Appearance.Definition == chick,
                    "Account clearing immediately restores preview presentation without owned binding");
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(actor);
                UnityEngine.Object.DestroyImmediate(chickModel); UnityEngine.Object.DestroyImmediate(birdModel);
                UnityEngine.Object.DestroyImmediate(chick); UnityEngine.Object.DestroyImmediate(bird);
                UnityEngine.Object.DestroyImmediate(world);
            }
        }

        private static void ValidateCompanionCareContracts()
        {
            string stableJson = ReadFixture("pets-stable.json");
            var stable = ApiContract.ParseStable(stableJson);
            Check(stable.total_pets == 3 && stable.total_mounts == 2 && stable.ActiveCompanion.id == 51 && stable.ActiveMount.id == 61,
                "Shared stable preserves authoritative creature counts and active IDs");
            Check(stable.ActiveCompanion.name == "Sprout {a} \"friend\"" && stable.ActiveCompanion.last_fed_at == null,
                "Shared companion preserves escaped names and absent feeding history");
            Check(ApiContract.ParseStable(ReadFixture("pets-stable-empty.json")).pets.Length == 0,
                "Shared empty collection never fabricates an owned creature");
            var restrictedStable = ApiContract.ParseStable(ReadFixture("pets-stable-restricted-empty.json"));
            Check(restrictedStable.total_possible == 3 && restrictedStable.pets.Length == 0
                && restrictedStable.mounts.Length == 0 && restrictedStable.ActiveCompanion == null,
                "Shared collection total counts compatible variants without inventing ownership");

            string inventoryJson = ReadFixture("inventory-food.json");
            var inventory = ApiContract.ParseInventoryPage(inventoryJson);
            Check(inventory.results.Length == 4 && inventory.count == 4 && inventory.next == null,
                "Shared bare inventory response preserves items without inventing pagination");
            int foods = 0;
            bool foundFavorite = false, foundNeutral = false, foundEgg = false;
            foreach (var entry in inventory.results)
            {
                if (entry.item.item_type == "food") foods++;
                if (entry.item.id == 71) foundFavorite = entry.quantity == 2 && entry.item.food_species_name == "Fox";
                if (entry.item.id == 72) foundNeutral = entry.quantity == 1 && entry.item.food_species_name == null;
                if (entry.item.id == 73) foundEgg = entry.item.item_type == "egg";
            }
            Check(foods == 3 && foundFavorite && foundNeutral && foundEgg,
                "Shared food and nonfood inventory preserve type, quantity and nullable preference");
            Check(ApiContract.ParseInventoryPage(ReadFixture("inventory-empty.json")).results.Length == 0,
                "Shared empty food inventory remains valid");
            var page = ApiContract.ParseInventoryPage("{\"count\":4,\"next\":null,\"results\":" + inventoryJson + "}");
            Check(page.results.Length == 4 && page.count == 4 && page.next == null, "Inventory accepts a bounded DRF page shape");
            string trimmedInventory = inventoryJson.Trim();
            string inventoryRecords = trimmedInventory.Substring(1, trimmedInventory.Length - 2);
            Reject(() => ApiContract.ParseInventoryPage("[" + inventoryRecords + "," + inventoryRecords + "]"), "Duplicate inventory rows cannot authorize extra feeds");
            Reject(() => ApiContract.ParseInventoryPage(inventoryJson.Replace("\"quantity\": 2", "\"quantity\": -1")), "Negative food quantities are rejected");
            Reject(() => ApiContract.ParseInventoryPage(inventoryJson.Replace("\"item_type\": \"food\"", "\"item_type\": null")), "Missing item types cannot become feed eligibility");
            Reject(() => ApiContract.ParseInventoryPage("{\"count\":10001,\"next\":null,\"results\":[]}"), "Inventory count is bounded");
            Reject(() => ApiContract.ParseInventoryPage("{\"count\":1,\"next\":\"?page=2\",\"results\":[]}"), "An empty inventory continuation is rejected");
            Check(AbbyApiClient.TryResolveInventoryPageUrl("https://abby.example.com", "/api/inventory/?page=2", out var next)
                && next == "https://abby.example.com/api/inventory/?page=2", "Food pages stay on the same-origin inventory endpoint");
            Check(AbbyApiClient.TryResolveInventoryPageUrl("https://abby.example.com", "/api/inventory/?page=2&_abby_session=0123456789abcdef0123456789abcdef", out next)
                && next == "https://abby.example.com/api/inventory/?page=2", "Food pagination strips the inherited private GET namespace");
            foreach (string unsafePage in new[] { "https://outside.example.com/api/inventory/?page=2", "http://abby.example.com/api/inventory/?page=2", "/api/auth/", "/api/inventory/?page=0", "/api/inventory/?page=501", "/api/inventory/?page=2&token=x", "/api/inventory/?page=2#secret", "https://user@abby.example.com/api/inventory/?page=2", "/api/inventory/?page=2&page=3", "/api/inventory/?page=2&_abby_session=bad" })
                Check(!AbbyApiClient.TryResolveInventoryPageUrl("https://abby.example.com", unsafePage, out _), "Unsafe food continuation rejected: " + unsafePage);

            string feedJson = ReadFixture("pet-feed.json");
            var feed = ApiContract.ParsePetFeed(feedJson, 20);
            Check(feed.growth_added == 15 && feed.new_growth == 35 && !feed.evolved && feed.mount_id == 0,
                "Shared confirmed feeding preserves growth without fabricating an evolved mount");
            var neutral = ApiContract.ParsePetFeed(ReadFixture("pet-feed-neutral.json"), 20);
            Check(neutral.growth_added == 5 && neutral.new_growth == 25, "Shared neutral feeding uses the server-confirmed outcome");
            string evolvedJson = ReadFixture("pet-feed-evolved.json");
            var evolved = ApiContract.ParsePetFeed(evolvedJson, 90);
            Check(evolved.growth_added == 15 && evolved.new_growth == 100 && evolved.evolved && evolved.mount_id == 83,
                "Shared evolution retains the clamped confirmed total and created mount ID");
            Reject(() => ApiContract.ParsePetFeed(feedJson.Replace("\"evolved\": false", "\"evolved\": \"false\"")), "Feeding confirmation requires an explicit evolution boolean");
            Reject(() => ApiContract.ParsePetFeed(feedJson.Replace("\"new_growth\": 35", "\"new_growth\": 101")), "Feeding cannot fabricate growth beyond evolution");
            Reject(() => ApiContract.ParsePetFeed(feedJson.Replace("\"mount_id\": null", "\"mount_id\": 83")), "Unevolved feeding cannot create a mount ID");
            Reject(() => ApiContract.ParsePetFeed(evolvedJson.Replace("\"mount_id\": 83", "\"mount_id\": null")), "Evolution must confirm the created mount");
            Reject(() => ApiContract.ParsePetFeed(evolvedJson.Replace("\"new_growth\": 100", "\"new_growth\": 99")), "Evolution requires the threshold total");
            Reject(() => ApiContract.ParsePetFeed(feedJson, 35), "An unchanged growth total cannot confirm feeding");

            OwnedPetDto expectedPet = null;
            OwnedMountDto expectedMount = null;
            foreach (var pet in stable.pets) if (pet.id == 52) expectedPet = pet;
            foreach (var mount in stable.mounts) if (mount.id == 62) expectedMount = mount;
            string activatedPetJson = ReadFixture("pet-activate.json");
            string activatedMountJson = ReadFixture("mount-activate.json");
            Check(ApiContract.ParsePetActivation(activatedPetJson, expectedPet).is_active,
                "Shared activation confirms the selected owned companion");
            Check(ApiContract.ParseMountActivation(activatedMountJson, expectedMount).is_active,
                "Shared activation confirms the selected owned mount");
            Reject(() => ApiContract.ParsePetActivation(activatedPetJson, stable.ActiveCompanion), "Another pet's response cannot confirm selection");
            Reject(() => ApiContract.ParseMountActivation(activatedMountJson, stable.ActiveMount), "Another mount's response cannot confirm selection");
            Reject(() => ApiContract.ParsePetActivation(activatedPetJson.Replace("\"is_active\": true", "\"is_active\": false"), expectedPet), "Inactive pet state cannot confirm selection");
            Reject(() => ApiContract.ParsePetActivation(activatedPetJson.Replace("\"evolved_to_mount\": false", "\"evolved_to_mount\": true"), expectedPet), "An evolved pet cannot become the active companion");
            Reject(() => ApiContract.ParseMountActivation(activatedMountJson.Replace("\"is_active\": true", "\"is_active\": false"), expectedMount), "Inactive mount state cannot confirm selection");
            const string expedition = "{\"id\":91,\"mount_id\":62,\"status\":\"active\",\"is_ready\":true,\"seconds_remaining\":-1}";
            string exploringMount = activatedMountJson.Replace("\"active_expedition\": null", "\"active_expedition\": " + expedition);
            Check(ApiContract.ParseOwnedMount(exploringMount).active_expedition.seconds_remaining == -1,
                "A returned but unclaimed expedition remains active and keeps Django's negative countdown");
            Reject(() => ApiContract.ParseMountActivation(exploringMount, expectedMount), "An exploring mount cannot confirm availability for selection");
            Reject(() => ApiContract.ParseOwnedMount(exploringMount.Replace("\"mount_id\":62", "\"mount_id\":61")), "An expedition must belong to its mount");
            foreach (string fixture in new[] { "pet-feed-missing-food.json", "pet-feed-unavailable-food.json", "pet-feed-already-evolved.json", "pet-not-owned.json", "mount-not-owned.json" })
                Check(!ApiContract.HttpError(400, ReadFixture(fixture), true, false).OutcomeUnknown, "Shared care rejection is definite: " + fixture);
        }

        private static void ValidateHatchingContracts()
        {
            string inventoryJson = ReadFixture("inventory-hatching.json");
            var inventory = ApiContract.ParseInventoryPage(inventoryJson);
            var egg = Array.Find(inventory.results, entry => entry.item.id == 73);
            var potion = Array.Find(inventory.results, entry => entry.item.id == 75);
            Check(egg != null && egg.id == 83 && egg.quantity == 2 && egg.item.item_type == "egg" && egg.item.pet_species_name == "Fox",
                "Hatching uses owned egg definition IDs, quantities and authoritative species names");
            Check(potion != null && potion.id == 85 && potion.quantity == 1 && potion.item.item_type == "potion" && potion.item.potion_type_name == "Ice",
                "Hatching uses owned potion definition IDs and authoritative potion names");
            string hatchJson = ReadFixture("pet-hatch.json");
            var previousIds = new HashSet<int>();
            foreach (var pet in ApiContract.ParseStable(ReadFixture("pets-stable.json")).pets) previousIds.Add(pet.id);
            var hatched = ApiContract.ParsePetHatch(hatchJson, egg.item, potion.item, previousIds);
            Check(hatched.id == 83 && hatched.species.id == 41 && hatched.potion.id == 44 && hatched.growth_points == 0
                && !hatched.is_active && !hatched.evolved_to_mount && !hatched.is_fully_grown && hatched.last_fed_at == null,
                "Shared hatch response confirms a new inactive, unfed companion with zero growth");
            Reject(() => ApiContract.ParsePetHatch(hatchJson, egg.item, potion.item, new HashSet<int> { 83 }),
                "An existing pet receipt cannot confirm another hatching");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"growth_points\": 0", "\"growth_points\": 5"), egg.item, potion.item, previousIds),
                "A grown creature cannot confirm a new hatch");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"is_active\": false", "\"is_active\": true"), egg.item, potion.item, previousIds),
                "Hatching cannot silently choose the active companion");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"evolved_to_mount\": false", "\"evolved_to_mount\": true"), egg.item, potion.item, previousIds),
                "An evolved creature cannot confirm a new hatch");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"last_fed_at\": null", "\"last_fed_at\": \"2026-10-10T12:00:00-07:00\""), egg.item, potion.item, previousIds),
                "A previously fed creature cannot confirm a new hatch");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"name\": \"Fox\"", "\"name\": \"Other species\""), egg.item, potion.item, previousIds),
                "The hatch receipt must match the typed egg species");
            Reject(() => ApiContract.ParsePetHatch(hatchJson.Replace("\"name\": \"Ice\"", "\"name\": \"Other potion\""), egg.item, potion.item, previousIds),
                "The hatch receipt must match the typed potion");
            Reject(() => ApiContract.ParsePetHatch(hatchJson, potion.item, egg.item, previousIds),
                "Swapped ingredient types cannot confirm hatching");
            Reject(() => ApiContract.ParseInventoryPage(inventoryJson.Replace("\"pet_species_name\": \"Fox\"", "\"pet_species_name\": 41")),
                "Typed ingredient names cannot become inferred catalog IDs");
            Reject(() => ApiContract.ParseInventoryPage(inventoryJson.Replace("\"potion_type_name\": \"Ice\"", "\"potion_type_name\": true")),
                "Typed potion names must be nullable strings");
            Check(ApiContract.ParsePetHatch(hatchJson, new InventoryItemDto { item_type = "egg" }, new InventoryItemDto { item_type = "potion" }, previousIds).id == 83,
                "Legacy ingredients without typed display names retain the server-confirmed hatch outcome");
            foreach (string fixture in new[] { "pet-hatch-missing-ingredients.json", "pet-hatch-unavailable-egg.json", "pet-hatch-unavailable-potion.json", "pet-hatch-duplicate.json" })
                Check(!ApiContract.HttpError(400, ReadFixture(fixture), true, false).OutcomeUnknown,
                    "Shared hatch rejection is definite and never a successful reveal: " + fixture);
        }

        private static void ValidateExpeditionContracts()
        {
            var stable = ApiContract.ParseStable(ReadFixture("pets-stable.json"));
            var shortMount = Array.Find(stable.mounts, mount => mount.id == 61);
            string shortJson = ReadFixture("expedition-start-short.json");
            var started = ApiContract.ParseExpeditionStart(shortJson, shortMount, "short", new HashSet<int>());
            Check(started.id == 103 && started.mount_id == 61 && started.status == "active" && !started.CanClaim
                && started.loot.coins == 15 && started.loot.items.Length == 1,
                "Shared start confirms a new owned expedition without awarding its locked loot");
            foreach (string tier in new[] { "standard", "long" })
            {
                var row = ApiContract.ParseExpedition(ReadFixture("expedition-start-" + tier + ".json"));
                Check(row.tier == tier && row.loot.items.Length == (tier == "standard" ? 2 : 3)
                    && row.loot.items[0].item_id == row.loot.items[1].item_id,
                    "Repeated rolled item slots remain legitimate: " + tier);
            }
            Reject(() => ApiContract.ParseExpeditionStart(shortJson, new OwnedMountDto { id = 62 }, "short", new HashSet<int>()),
                "A start receipt for another mount cannot confirm the requested expedition");
            Reject(() => ApiContract.ParseExpeditionStart(shortJson, shortMount, "long", new HashSet<int>()),
                "A different tier cannot confirm an expedition start");
            Reject(() => ApiContract.ParseExpeditionStart(shortJson, shortMount, "short", new HashSet<int> { started.id }),
                "A historical expedition cannot confirm another start");
            Reject(() => ApiContract.ParseExpedition(shortJson.Replace("\"tier\": \"short\"", "\"tier\": \"overnight\"")),
                "Unknown expedition tiers are rejected");
            Reject(() => ApiContract.ParseExpedition(shortJson.Replace("\"is_ready\": false", "\"is_ready\": \"false\"")),
                "Readiness cannot default from an invalid boolean");
            var approaching = ApiContract.ParseExpedition(shortJson);
            approaching.seconds_remaining = 0;
            Check(!approaching.CanClaim, "A zero displayed countdown does not establish server readiness");
            var legacy = ApiContract.ParseExpedition(shortJson.Replace("\"species_slug\": \"fixture-fox\"", "\"species_slug\": null")
                .Replace("\"potion_slug\": \"ice\"", "\"potion_slug\": null"));
            Check(legacy.species_slug == null && legacy.potion_slug == null, "Nullable legacy catalog slugs retain their absent identity semantics");

            var history = ApiContract.ParseExpeditions(ReadFixture("expeditions.json"));
            var readyRows = ApiContract.ParseExpeditions(ReadFixture("expeditions-ready.json"));
            var ready = Array.Find(readyRows, row => row.id == started.id);
            Check(history.Length > 0 && ready != null && ready.CanClaim && ready.seconds_remaining <= 0,
                "Shared history and ready rows retain signed countdowns and authoritative lifecycle state");
            Check(ApiContract.ParseExpeditions(ReadFixture("expeditions-empty.json")).Length == 0, "Empty expedition history remains an acknowledged read");
            Reject(() => ApiContract.ParseExpeditions("{\"expeditions\":[" + shortJson + "," + shortJson + "]}"), "Duplicate expedition identities cannot authorize additional claims");
            Reject(() => ApiContract.ParseExpeditions("{}"), "A missing expedition collection cannot masquerade as empty history");
            string claimJson = ReadFixture("expedition-claim.json");
            var claimed = ApiContract.ParseExpeditionClaim(claimJson, ready);
            Check(claimed.expedition_id == ready.id && claimed.mount.id == ready.mount_id && claimed.coins_awarded == 15
                && claimed.freshly_claimed && claimed.items.Length == ready.loot.items.Length,
                "Shared claim confirms the matching expedition's actual primary coin award and recorded item slots");
            var repeat = ApiContract.ParseExpeditionClaim(ReadFixture("expedition-claim-repeat.json"), ready);
            Check(!repeat.freshly_claimed && repeat.coins_awarded == 0 && repeat.items.Length == claimed.items.Length,
                "An already claimed receipt confirms zero new coins and cannot trigger another celebration");
            var claimContext = ApiContract.ParseExpeditions(ReadFixture("expeditions-ready-claim.json"))[0];
            var boosted = ApiContract.ParseExpeditionClaim(ReadFixture("expedition-claim-boosted.json"), claimContext);
            Check(boosted.freshly_claimed && boosted.coins_awarded == 30 && claimContext.loot.coins == 15,
                "The actual Lucky Coin ledger award may exceed the locked base coin plan");
            var archived = ApiContract.ParseExpeditionClaim(ReadFixture("expedition-claim-archived-item.json"), claimContext);
            Check(archived.freshly_claimed && archived.items[0].item_id == 71,
                "A skipped archived slot remains recorded loot without claiming it is current inventory");
            var salvageContext = ApiContract.ParseExpeditions(ReadFixture("expeditions-ready-salvage.json"))[0];
            string salvageJson = ReadFixture("expedition-claim-salvage.json");
            var salvaged = ApiContract.ParseExpeditionClaim(salvageJson, salvageContext);
            Check(salvaged.coins_awarded == 15 && salvaged.items[0].salvaged_to_coins == 20,
                "Duplicate cosmetic salvage stays separate from the confirmed primary coin award");
            Reject(() => ApiContract.ParseExpeditionClaim(salvageJson.Replace("\"salvaged_to_coins\": 20", "\"salvaged_to_coins\": -1"), salvageContext),
                "Invalid salvage values cannot become a confirmed coin description");
            Reject(() => ApiContract.ParseExpeditionClaim(claimJson.Replace("\"expedition_id\": 103", "\"expedition_id\": 104"), ready),
                "Another expedition's receipt cannot confirm this claim");
            Reject(() => ApiContract.ParseExpeditionClaim(claimJson.Replace("\"id\": 61", "\"id\": 62"), ready),
                "A claim must identify the owned expedition's mount");
            Reject(() => ApiContract.ParseExpeditionClaim(claimJson.Replace("\"coins_awarded\": 15", "\"coins_awarded\": -1"), ready),
                "A negative coin amount cannot confirm a reward");
            Reject(() => ApiContract.ParseExpeditionClaim(claimJson.Replace("\"coins_awarded\": 15", "\"coins_awarded\": 0"), ready),
                "A fresh claim must confirm at least its locked primary coin plan");
            Reject(() => ApiContract.ParseExpeditionClaim(claimJson.Replace("\"freshly_claimed\": true", "\"freshly_claimed\": \"true\""), ready),
                "Claim freshness requires an explicit boolean");
            Reject(() => ApiContract.ParseExpeditionClaim(claimJson.Replace("\"freshly_claimed\": true", "\"freshly_claimed\": false"), ready),
                "An already claimed receipt cannot confirm newly awarded coins");
            Reject(() => ApiContract.ParseExpeditionClaim(claimJson.Replace("\"quantity\": 1", "\"quantity\": 2"), ready),
                "A receipt cannot increase the locked loot quantity");
            Reject(() => ApiContract.ParseExpeditionClaim(claimJson, started), "An outbound row cannot authorize a claim confirmation");
            foreach (string fixture in new[] { "expedition-invalid-tier.json", "expedition-mount-not-owned.json", "expedition-not-owned.json",
                "expedition-early-claim.json", "expedition-already-active.json", "expedition-daily-limit.json", "expedition-expired.json" })
                Check(!ApiContract.HttpError(fixture.Contains("not-owned") ? 404 : 400, ReadFixture(fixture), true, false).OutcomeUnknown,
                    "Shared expedition rejection requires a refresh without a fabricated reward: " + fixture);

            var gameObject = new GameObject("Expedition eligibility validation");
            try
            {
                var client = gameObject.AddComponent<AbbyApiClient>();
                void Set(string field, object value) => typeof(AbbyApiClient).GetField(field, BindingFlags.Instance | BindingFlags.NonPublic).SetValue(client, value);
                Set("token", "0123456789012345678901234567890123456789");
                Set("<CurrentUser>k__BackingField", new UserDto { id = 7, role = "child" });
                Set("stableLoaded", true); Set("expeditionsLoaded", true);
                var mounts = (Dictionary<int, OwnedMountDto>)typeof(AbbyApiClient).GetField("knownMounts", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(client);
                var rows = (Dictionary<int, ExpeditionDto>)typeof(AbbyApiClient).GetField("knownExpeditions", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(client);
                var readyIds = (HashSet<int>)typeof(AbbyApiClient).GetField("readyExpeditions", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(client);
                mounts.Add(shortMount.id, shortMount);
                Check(shortMount.is_active && client.CanStartExpedition(shortMount.id, "short"), "An owned active mount can start an expedition as the existing server allows");
                Check(!client.CanStartExpedition(999, "short") && !client.CanStartExpedition(shortMount.id, "unknown"),
                    "Foreign identities and unsupported tiers never become start eligibility");
                shortMount.active_expedition = new MountExpeditionDto { id = ready.id, mount_id = shortMount.id, status = "active", is_ready = true };
                rows.Add(ready.id, ready); readyIds.Add(ready.id);
                Check(!client.CanStartExpedition(shortMount.id, "short") && client.CanClaimExpedition(ready.id) && !client.CanClaimExpedition(999),
                    "An exploring mount blocks another start while its accepted own ready row enables one claim");
                readyIds.Clear();
                Check(!client.CanClaimExpedition(ready.id), "A locally changed DTO cannot replace readiness captured from an accepted server read");
                readyIds.Add(ready.id);
                ready.status = "claimed";
                Check(!client.CanClaimExpedition(ready.id), "A ready claimed history row cannot authorize another claim");
                ready.status = "active";
                Set("stableLoaded", false);
                Check(!client.CanClaimExpedition(ready.id), "Claims require a fresh complete owned stable snapshot");
                Set("stableLoaded", true); Set("expeditionsLoaded", false);
                Check(!client.CanClaimExpedition(ready.id), "Claims require a fresh complete expedition snapshot");
                Set("expeditionsLoaded", true); Set("<MutationInFlight>k__BackingField", true);
                Check(!client.CanClaimExpedition(ready.id), "The shared mutation lock blocks concurrent expedition actions");
                Set("<MutationInFlight>k__BackingField", false);
                ApiError rejection = null;
                bool completed = false;
                var coroutine = client.StartExpedition(61, "unknown", _ => completed = true, error => rejection = error);
                Check(!coroutine.MoveNext() && !completed && rejection != null && !rejection.OutcomeUnknown,
                    "An unsupported start is rejected before any request dispatch");
                rejection = null;
                coroutine = client.ClaimExpedition(999, _ => completed = true, error => rejection = error);
                Check(!coroutine.MoveNext() && !completed && rejection != null && !rejection.OutcomeUnknown,
                    "An unknown claim is rejected before any request dispatch");
                client.ClearSession();
                Check(rows.Count == 0 && mounts.Count == 0 && readyIds.Count == 0 && !client.CanClaimExpedition(ready.id),
                    "Account replacement clears every expedition identity and readiness cache");
            }
            finally { UnityEngine.Object.DestroyImmediate(gameObject); }
        }

        private static void ValidateBreedingContracts()
        {
            string stableJson = ReadFixture("pets-stable-breeding.json");
            var stable = ApiContract.ParseStable(stableJson);
            var parentA = Array.Find(stable.mounts, mount => mount.id == 61);
            var parentB = Array.Find(stable.mounts, mount => mount.id == 62);
            var resting = Array.Find(stable.mounts, mount => mount.id == 63);
            Check(parentA.can_breed && parentA.breeding_cooldown_seconds == 0 && parentA.active_expedition != null
                && parentB.can_breed && parentB.breeding_cooldown_seconds == 0,
                "Shared stable reports server-ready parents, including an exploring parent and an elapsed cooldown");
            Check(!resting.can_breed && resting.breeding_cooldown_seconds == 432000,
                "Shared stable preserves the authoritative remaining breeding cooldown");
            var after = ApiContract.ParseStable(ReadFixture("pets-stable-breeding-after.json"));
            Check(!Array.Find(after.mounts, mount => mount.id == 61).can_breed
                && Array.Find(after.mounts, mount => mount.id == 61).breeding_cooldown_seconds == 604800
                && !Array.Find(after.mounts, mount => mount.id == 62).can_breed,
                "A fresh post-breeding stable reports both parents' saved cooldowns");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"can_breed\":", "\"omitted_can_breed\":")),
                "Missing breeding readiness cannot default to an eligible mount");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"breeding_cooldown_seconds\":", "\"omitted_cooldown\":")),
                "A missing cooldown cannot masquerade as completed rest");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"can_breed\": true", "\"can_breed\": \"true\"")),
                "Breeding readiness must be a JSON boolean");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"breeding_cooldown_seconds\": 0", "\"breeding_cooldown_seconds\": -1")),
                "Negative breeding cooldowns are rejected");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"breeding_cooldown_seconds\": 0", "\"breeding_cooldown_seconds\": 0.5")),
                "Fractional seconds cannot silently round into breeding readiness");
            Reject(() => ApiContract.ParseStable(stableJson.Replace("\"can_breed\": false", "\"can_breed\": true")),
                "Positive remaining rest cannot be marked ready by an inconsistent response");

            string normalJson = ReadFixture("mount-breed.json");
            var normal = ApiContract.ParseMountBreed(normalJson, parentA, parentB);
            Check(normal.egg_item_id == 73 && normal.potion_item_id == 77 && normal.picked_species == "Fox"
                && normal.picked_species_slug == "fixture-fox" && normal.picked_potion == "Ice"
                && normal.picked_potion_slug == "ice" && !normal.chromatic && normal.cooldown_days == 7,
                "The real normal breeding receipt confirms the saved egg and potion definitions and chosen types");
            Check(!string.IsNullOrWhiteSpace(normal.egg_item_name) && normal.egg_item_icon != null && normal.egg_item_sprite_key != null
                && !string.IsNullOrWhiteSpace(normal.potion_item_name) && normal.potion_item_icon != null && normal.potion_item_sprite_key != null,
                "A complete breeding receipt preserves both result items' display metadata");
            var chromatic = ApiContract.ParseMountBreed(ReadFixture("mount-breed-chromatic.json"), parentA, parentB);
            Check(chromatic.chromatic && chromatic.picked_potion_slug == "cosmic" && chromatic.potion_item_id == 78,
                "The server's chromatic result confirms its saved Cosmic potion");
            var fallback = ApiContract.ParseMountBreed(ReadFixture("mount-breed-fallback.json"), parentA, parentB);
            Check(!fallback.chromatic && fallback.picked_potion == "Base" && fallback.potion_item_id == 79
                && fallback.picked_potion != parentA.potion.name && fallback.picked_potion != parentB.potion.name,
                "A server-selected compatible fallback need not be either parent's potion");
            foreach (string field in new[] { "egg_item_id", "egg_item_name", "egg_item_icon", "egg_item_sprite_key",
                "potion_item_id", "potion_item_name", "potion_item_icon", "potion_item_sprite_key", "picked_species",
                "picked_species_slug", "picked_potion", "picked_potion_slug", "chromatic", "cooldown_days" })
                Reject(() => ApiContract.ParseMountBreed(normalJson.Replace("\"" + field + "\":", "\"omitted_" + field + "\":"), parentA, parentB),
                    "A partial success cannot acknowledge breeding when this field is absent: " + field);
            string Changed(Action<MountBreedDto> change)
            {
                var receipt = JsonUtility.FromJson<MountBreedDto>(normalJson);
                change(receipt);
                return JsonUtility.ToJson(receipt);
            }
            Reject(() => ApiContract.ParseMountBreed(Changed(receipt => receipt.egg_item_id = 0), parentA, parentB),
                "Breeding must confirm a real saved egg item ID");
            Reject(() => ApiContract.ParseMountBreed(Changed(receipt => receipt.potion_item_id = receipt.egg_item_id), parentA, parentB),
                "An egg cannot also be the breeding potion definition");
            Reject(() => ApiContract.ParseMountBreed(Changed(receipt => receipt.cooldown_days = 0), parentA, parentB),
                "A missing or invalid saved cooldown cannot confirm breeding");
            Reject(() => ApiContract.ParseMountBreed(Changed(receipt => receipt.picked_species = "Unrelated creature"), parentA, parentB),
                "A breeding receipt must select one of the captured parents' unique species names");
            Reject(() => ApiContract.ParseMountBreed(Changed(receipt => receipt.picked_potion_slug = "unrelated"), parentA, parentB),
                "A known parental potion name cannot silently acquire an unrelated slug");
            Reject(() => ApiContract.ParseMountBreed(Changed(receipt => receipt.chromatic = true), parentA, parentB),
                "The chromatic flag cannot turn an ordinary parental potion into Cosmic");
            Reject(() => ApiContract.ParseMountBreed(normalJson.Replace("\"chromatic\": false", "\"chromatic\": \"false\""), parentA, parentB),
                "A string chromatic flag cannot acknowledge a saved breeding");
            Reject(() => ApiContract.ParseMountBreed(normalJson, parentA, parentA),
                "A breeding receipt needs two distinct captured parent identities");
            Reject(() => ApiContract.ParseMountBreed(normalJson, parentA, resting),
                "A captured cooldown mount cannot authorize a breeding acknowledgement");
            var legacyA = JsonUtility.FromJson<OwnedMountDto>(JsonUtility.ToJson(parentA));
            var legacyB = JsonUtility.FromJson<OwnedMountDto>(JsonUtility.ToJson(parentB));
            legacyA.potion.slug = legacyB.potion.slug = null;
            string legacyJson = normalJson.Replace("\"picked_species_slug\": \"fixture-fox\"", "\"picked_species_slug\": null")
                .Replace("\"picked_potion_slug\": \"ice\"", "\"picked_potion_slug\": null");
            Check(ApiContract.ParseMountBreed(legacyJson, legacyA, legacyB).egg_item_id == 73,
                "Legacy nullable catalog slugs do not invent a type or reject a complete saved result");
            foreach (string fixture in new[] { "mount-breed-missing-mounts.json", "mount-breed-same-mount.json", "mount-breed-invalid-ids.json",
                "mount-breed-not-owned.json", "mount-breed-cooldown.json", "mount-breed-repeat-cooldown.json" })
                Check(!ApiContract.HttpError(400, ReadFixture(fixture), true, false).OutcomeUnknown,
                    "A real breeding rejection is definite and grants no fabricated result: " + fixture);

            var gameObject = new GameObject("Breeding eligibility validation");
            try
            {
                var client = gameObject.AddComponent<AbbyApiClient>();
                void Set(string field, object value) => typeof(AbbyApiClient).GetField(field, BindingFlags.Instance | BindingFlags.NonPublic).SetValue(client, value);
                Set("token", "0123456789012345678901234567890123456789");
                Set("<CurrentUser>k__BackingField", new UserDto { id = 7, role = "child" });
                Set("stableLoaded", true);
                var mounts = (Dictionary<int, OwnedMountDto>)typeof(AbbyApiClient).GetField("knownMounts", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(client);
                var readyIds = (HashSet<int>)typeof(AbbyApiClient).GetField("breedableMounts", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(client);
                foreach (var mount in stable.mounts) mounts.Add(mount.id, mount);
                readyIds.Add(parentA.id); readyIds.Add(parentB.id);
                Check(client.IsBreedableMount(parentA.id) && client.CanBreedMounts(parentA.id, parentB.id),
                    "Only accepted ready owned parents authorize an explicit breeding, including an away parent");
                parentB.active_expedition = new MountExpeditionDto { id = 104, mount_id = parentB.id, status = "active" };
                Check(client.CanBreedMounts(parentA.id, parentB.id),
                    "Even two away parents retain breeding eligibility under the existing server behavior");
                Check(!client.CanBreedMounts(parentA.id, parentA.id) && !client.CanBreedMounts(parentA.id, 999)
                    && !client.CanBreedMounts(0, parentB.id) && !client.IsBreedableMount(resting.id),
                    "Same, absent, foreign and resting parent selections cannot issue breeding");
                resting.can_breed = true; resting.breeding_cooldown_seconds = 0;
                Check(!client.CanBreedMounts(parentA.id, resting.id),
                    "Changing a displayed countdown or DTO cannot replace captured server readiness");
                Set("stableLoaded", false);
                Check(!client.IsBreedableMount(parentA.id), "An incomplete or failed stable read disables breeding");
                Set("stableLoaded", true);
                Set("<CurrentUser>k__BackingField", new UserDto { id = 7, role = "parent" });
                Check(!client.CanBreedMounts(parentA.id, parentB.id), "Parent sessions cannot use native child breeding");
                Set("<CurrentUser>k__BackingField", new UserDto { id = 7, role = "child" });
                Set("<MutationInFlight>k__BackingField", true);
                Check(!client.CanBreedMounts(parentA.id, parentB.id), "The shared care mutation lock blocks another breeding");
                Set("<MutationInFlight>k__BackingField", false);
                ApiError rejection = null;
                bool completed = false;
                var coroutine = client.BreedMounts(parentA.id, parentA.id, _ => completed = true, error => rejection = error);
                Check(!coroutine.MoveNext() && !completed && rejection != null && !rejection.OutcomeUnknown,
                    "An ineligible pair is rejected before request dispatch");
                rejection = null;
                coroutine = client.BreedMounts(parentA.id, 999, _ => completed = true, error => rejection = error);
                Check(!coroutine.MoveNext() && !completed && rejection != null && !rejection.OutcomeUnknown,
                    "An unfetched parent cannot send a breeding request");
                coroutine = client.BreedMounts(parentA.id, parentB.id, _ => completed = true, error => rejection = error);
                Check(coroutine.MoveNext() && !completed && mounts.Count == 0 && readyIds.Count == 0 && !client.IsBreedableMount(parentA.id),
                    "Preparing one explicit breeding invalidates all previous care and breeding eligibility before sending");
                (coroutine as IDisposable)?.Dispose();
                mounts.Add(parentA.id, parentA); readyIds.Add(parentA.id); Set("stableLoaded", true);
                client.ClearSession();
                Check(mounts.Count == 0 && readyIds.Count == 0 && !client.IsBreedableMount(parentA.id),
                    "Account replacement clears every owned breeding identity and readiness snapshot");
            }
            finally { UnityEngine.Object.DestroyImmediate(gameObject); }
        }

        private static void ValidateCareRefreshLock()
        {
            var gameObject = new GameObject("Care refresh ownership validation");
            System.Collections.IEnumerator heldRefresh = null;
            try
            {
                var client = gameObject.AddComponent<AbbyApiClient>();
                var controller = gameObject.AddComponent<AbbyCamp.UI.CampPrototypeController>();
                const BindingFlags privateInstance = BindingFlags.Instance | BindingFlags.NonPublic;
                typeof(AbbyApiClient).GetField("token", privateInstance).SetValue(client, "0123456789012345678901234567890123456789");
                typeof(AbbyApiClient).GetField("<CurrentUser>k__BackingField", privateInstance).SetValue(client, new UserDto { id = 7, role = "child" });
                var controllerType = typeof(AbbyCamp.UI.CampPrototypeController);
                void Set(string field, object value) => controllerType.GetField(field, privateInstance).SetValue(controller, value);
                Set("api", client); Set("careInFlight", true);
                var sectionType = controllerType.GetNestedType("Section", BindingFlags.NonPublic);
                var bestiary = Enum.Parse(sectionType, "Bestiary");
                var loader = controllerType.GetMethod("LoadSection", privateInstance);
                System.Collections.IEnumerator Load(bool internalRefresh) => (System.Collections.IEnumerator)loader.Invoke(controller, new object[] { bestiary, internalRefresh });

                Check(!Load(false).MoveNext() && !controller.IsSectionLoading && controller.IsBusy,
                    "Ordinary collection refresh cannot enter or release an active care save");
                // Leave the visible section closed so presentation remains inert.
                // Advance the real loader to its first nested read without
                // advancing that request or opening any network connection.
                heldRefresh = Load(true);
                Check(heldRefresh.MoveNext() && heldRefresh.Current is System.Collections.IEnumerator
                    && controller.IsSectionLoading && controller.IsBusy,
                    "A save's internal collection refresh starts while that save retains its busy ownership");
                // Disposing exercises the loader's actual finally. Inner
                // teardown must never release its outer save's ownership.
                (heldRefresh as IDisposable)?.Dispose(); heldRefresh = null;
                Check(!controller.IsSectionLoading && controller.IsBusy,
                    "Nested refresh teardown clears loading without unlocking the outer care action");
                Check(!Load(false).MoveNext() && !controller.IsSectionLoading,
                    "After nested teardown the still-owned care save blocks the next ordinary refresh");
                Set("busy", true);
                Check(!Load(true).MoveNext() && !controller.IsSectionLoading,
                    "The internal care exception cannot bypass an independent connection busy gate");
                Set("busy", false); Set("markingRead", true);
                Check(!Load(true).MoveNext() && !controller.IsSectionLoading,
                    "The internal care exception cannot bypass an inbox acknowledgement busy gate");
            }
            finally
            {
                (heldRefresh as IDisposable)?.Dispose();
                UnityEngine.Object.DestroyImmediate(gameObject);
            }
        }

        private static void Check(bool condition, string description)
        {
            checks++;
            if (!condition) throw new InvalidOperationException("API contract validation failed: " + description);
        }

        private static void Reject(Action parse, string description)
        {
            bool rejected = false;
            try { parse(); }
            catch (FormatException) { rejected = true; }
            catch (ArgumentException) { rejected = true; }
            Check(rejected, description);
        }
    }
}
