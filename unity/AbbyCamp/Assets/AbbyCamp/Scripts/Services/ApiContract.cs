using System;
using System.Collections.Generic;
using System.Globalization;
using AbbyCamp.Data;
using UnityEngine;

namespace AbbyCamp.Services
{
    /// <summary>JsonUtility DTO parsing plus required-field checks. Missing approval
    /// flags must never default into permission to perform a real habit action.</summary>
    public static class ApiContract
    {
        [Serializable] private sealed class TokenPayload { public string token; }
        [Serializable] private sealed class ErrorPayload { public string error; public string detail; }
        [Serializable] private sealed class StringPayload { public string value; }

        public static UserDto ParseLogin(string json, out string token)
        {
            var user = ParseUser(json);
            token = JsonUtility.FromJson<TokenPayload>(json).token;
            if (string.IsNullOrEmpty(token) || token.Length != 40)
                throw new FormatException("The login response did not include a valid session token.");
            foreach (char character in token)
                if (!Uri.IsHexDigit(character))
                    throw new FormatException("The login response included an invalid session token.");
            return user;
        }

        public static UserDto ParseUser(string json)
        {
            var fields = ReadObject(json);
            RequireInteger(fields, "id", 1);
            RequireString(fields, "username");
            RequireString(fields, "role");
            var user = JsonUtility.FromJson<UserDto>(json);
            if (string.IsNullOrWhiteSpace(user.username) || (user.role != "child" && user.role != "parent"))
                throw new FormatException("The server returned an incomplete account.");
            return user;
        }

        public static CharacterDto ParseCharacter(string json)
        {
            var fields = ReadObject(json);
            RequireInteger(fields, "id", 1);
            RequireInteger(fields, "level", 0);
            RequireInteger(fields, "login_streak", 0);
            RequireString(fields, "username");
            return JsonUtility.FromJson<CharacterDto>(json);
        }

        public static CoinBalanceDto ParseCoins(string json, int userId)
        {
            if (userId < 1) throw new FormatException("A validated account is required for coin history.");
            var fields = ReadObject(json);
            int balance = RequireInteger(fields, "balance", int.MinValue);
            var records = BoundedRecords(Require(fields, "recent_transactions"), 10);
            var result = new CoinBalanceDto { balance = balance, recent_transactions = new CoinTransactionDto[records.Count] };
            var ids = new HashSet<int>();
            for (int index = 0; index < records.Count; index++)
            {
                var row = ReadObject(records[index]);
                int id = RequireInteger(row, "id", 1);
                if (!ids.Add(id) || RequireInteger(row, "user", 1) != userId)
                    throw new FormatException("The coin history does not belong to this account.");
                RequireInteger(row, "amount", int.MinValue);
                BoundedString(row, "reason", 100, true);
                BoundedString(row, "description", 400);
                RequiredDate(row, "created_at");
                result.recent_transactions[index] = JsonUtility.FromJson<CoinTransactionDto>(records[index]);
            }
            return result;
        }

        public static DropDto[] ParseRecentDrops(string json)
        {
            var records = BoundedRecords(json, 10);
            var result = new DropDto[records.Count];
            var ids = new HashSet<int>();
            for (int index = 0; index < records.Count; index++)
            {
                var row = ReadObject(records[index]);
                if (!ids.Add(RequireInteger(row, "id", 1))) throw new FormatException("The drop history contains duplicate records.");
                RequireInteger(row, "item", 1);
                RequireInteger(row, "quantity", 1);
                RequireBoolean(row, "was_salvaged");
                BoundedString(row, "item_name", 200, true);
                BoundedString(row, "item_icon", 100);
                BoundedString(row, "item_sprite_key", 100);
                BoundedString(row, "item_rarity", 40, true);
                BoundedString(row, "trigger_type", 100, true);
                RequiredDate(row, "created_at");
                result[index] = JsonUtility.FromJson<DropDto>(records[index]);
            }
            return result;
        }

        public static NotificationDto ParseNotification(string json)
        {
            var row = ReadObject(json);
            RequireInteger(row, "id", 1);
            RequireBoolean(row, "is_read");
            BoundedString(row, "title", 400, true);
            BoundedString(row, "message", 16384);
            BoundedString(row, "notification_type", 100, true);
            BoundedString(row, "link", 512);
            RequiredDate(row, "created_at");
            return JsonUtility.FromJson<NotificationDto>(json);
        }

        public static NotificationPageDto ParseNotificationPage(string json)
        {
            var fields = ReadObject(json);
            int count = RequireInteger(fields, "count", 0);
            var records = BoundedRecords(Require(fields, "results"), 20);
            if (records.Count > count) throw new FormatException("The notification count is smaller than its page.");
            var result = new NotificationPageDto { count = count, next = NullableString(fields, "next", 2048), results = new NotificationDto[records.Count] };
            if (result.next != null && (result.next.Length == 0 || records.Count == 0))
                throw new FormatException("The notification page has an invalid continuation.");
            var ids = new HashSet<int>();
            for (int index = 0; index < records.Count; index++)
            {
                result.results[index] = ParseNotification(records[index]);
                if (!ids.Add(result.results[index].id)) throw new FormatException("The notification page contains duplicate records.");
            }
            return result;
        }

        public static UnreadCountDto ParseUnreadCount(string json)
        {
            return new UnreadCountDto { count = RequireInteger(ReadObject(json), "count", 0) };
        }

        public static StableDto ParseStable(string json)
        {
            var fields = ReadObject(json);
            var pets = BoundedRecords(Require(fields, "pets"), 2048);
            var mounts = BoundedRecords(Require(fields, "mounts"), 2048);
            int totalPets = RequireInteger(fields, "total_pets", 0);
            int totalMounts = RequireInteger(fields, "total_mounts", 0);
            int possible = RequireInteger(fields, "total_possible", 0);
            if (totalPets != pets.Count || totalMounts != mounts.Count)
                throw new FormatException("The stable counts do not match its owned collection.");
            var result = new StableDto { pets = new OwnedPetDto[pets.Count], mounts = new OwnedMountDto[mounts.Count], total_pets = totalPets, total_mounts = totalMounts, total_possible = possible };
            var ids = new HashSet<int>();
            for (int index = 0; index < pets.Count; index++)
            {
                var pet = ParseOwnedPet(pets[index]);
                if (!ids.Add(pet.id)) throw new FormatException("The stable contains duplicate pets.");
                result.pets[index] = pet;
            }
            ids.Clear();
            for (int index = 0; index < mounts.Count; index++)
            {
                var mount = ParseOwnedMount(mounts[index]);
                if (!ids.Add(mount.id)) throw new FormatException("The stable contains duplicate mounts.");
                result.mounts[index] = mount;
            }
            return result;
        }

        public static OwnedPetDto ParseOwnedPet(string json)
        {
            var row = ReadObject(json);
            RequireInteger(row, "id", 1);
            ValidateOwnedCreature(row);
            int growth = RequireInteger(row, "growth_points", 0);
            if (growth > 100) throw new FormatException("The companion growth is outside its supported range.");
            RequireBoolean(row, "evolved_to_mount");
            RequireBoolean(row, "is_fully_grown");
            BoundedString(row, "name", 100);
            string happiness = BoundedString(row, "happiness_level", 40, true);
            if (happiness != "happy" && happiness != "bored" && happiness != "stale" && happiness != "away")
                throw new FormatException("The companion has an unknown happiness state.");
            var pet = JsonUtility.FromJson<OwnedPetDto>(json);
            pet.last_fed_at = NullableDate(row, "last_fed_at");
            if (pet.is_fully_grown != (growth >= 100)) throw new FormatException("The companion growth flags are inconsistent.");
            return pet;
        }

        public static OwnedMountDto ParseOwnedMount(string json)
        {
            var row = ReadObject(json);
            int id = RequireInteger(row, "id", 1);
            ValidateOwnedCreature(row);
            var mount = JsonUtility.FromJson<OwnedMountDto>(json);
            mount.last_bred_at = NullableDate(row, "last_bred_at");
            string expeditionJson = Require(row, "active_expedition");
            mount.active_expedition = null;
            if (expeditionJson != "null")
            {
                var expedition = ReadObject(expeditionJson);
                RequireInteger(expedition, "id", 1);
                if (RequireInteger(expedition, "mount_id", 1) != id || BoundedString(expedition, "status", 40, true) != "active")
                    throw new FormatException("The active expedition does not belong to this mount.");
                RequireBoolean(expedition, "is_ready");
                // Django returns negative seconds after return, and truncates
                // fractional seconds to zero just before is_ready becomes true.
                RequireInteger(expedition, "seconds_remaining", int.MinValue);
                mount.active_expedition = JsonUtility.FromJson<MountExpeditionDto>(expeditionJson);
            }
            return mount;
        }

        public static PetFeedDto ParsePetFeed(string json)
        {
            var row = ReadObject(json);
            int growth = RequireInteger(row, "growth_added", 1);
            int total = RequireInteger(row, "new_growth", 0);
            RequireBoolean(row, "evolved");
            int mount = Require(row, "mount_id") == "null" ? 0 : RequireInteger(row, "mount_id", 1);
            var result = new PetFeedDto { growth_added = growth, new_growth = total, evolved = Require(row, "evolved") == "true", mount_id = mount };
            if (growth > 100 || total > 100 || result.evolved != (mount > 0) || result.evolved != (total == 100))
                throw new FormatException("The server did not confirm a consistent feeding outcome.");
            return result;
        }

        public static PetFeedDto ParsePetFeed(string json, int previousGrowth)
        {
            var result = ParsePetFeed(json);
            if (previousGrowth < 0 || previousGrowth >= 100 || result.new_growth <= previousGrowth)
                throw new FormatException("The server did not confirm increased growth for this companion.");
            return result;
        }

        public static OwnedPetDto ParsePetActivation(string json, OwnedPetDto expected)
        {
            var result = ParseOwnedPet(json);
            if (expected == null || result.id != expected.id || result.species.id != expected.species.id || result.potion.id != expected.potion.id
                || !result.is_active || result.evolved_to_mount)
                throw new FormatException("The server did not confirm this companion as active.");
            return result;
        }

        public static OwnedMountDto ParseMountActivation(string json, OwnedMountDto expected)
        {
            var result = ParseOwnedMount(json);
            if (expected == null || result.id != expected.id || result.species.id != expected.species.id || result.potion.id != expected.potion.id
                || !result.is_active || result.active_expedition != null)
                throw new FormatException("The server did not confirm this available mount as active.");
            return result;
        }

        public static OwnedPetDto ParsePetHatch(string json, InventoryItemDto egg, InventoryItemDto potion, ICollection<int> previousPetIds)
        {
            var result = ParseOwnedPet(json);
            if (egg == null || egg.item_type != "egg" || potion == null || potion.item_type != "potion" || previousPetIds == null
                || previousPetIds.Contains(result.id) || result.growth_points != 0 || result.is_active
                || result.evolved_to_mount || result.is_fully_grown || result.last_fed_at != null)
                throw new FormatException("The server did not confirm a newly hatched companion.");
            // Typed display names are the identity information exposed by the
            // inventory API. Legacy items can omit them; never infer catalog IDs.
            if ((!string.IsNullOrEmpty(egg.pet_species_name) && egg.pet_species_name != result.species.name)
                || (!string.IsNullOrEmpty(potion.potion_type_name) && potion.potion_type_name != result.potion.name))
                throw new FormatException("The hatched companion does not match the selected egg and potion.");
            return result;
        }

        /// <summary>The current endpoint returns a bare array. Bounded DRF pages
        /// are also accepted so continuation URLs can be checked before use.</summary>
        public static InventoryPageDto ParseInventoryPage(string json)
        {
            if (string.IsNullOrWhiteSpace(json)) throw new FormatException("The inventory response was empty.");
            List<string> records;
            var result = new InventoryPageDto();
            if (json.TrimStart().StartsWith("[", StringComparison.Ordinal))
            {
                records = BoundedRecords(json, 10000);
                result.count = records.Count;
            }
            else
            {
                var fields = ReadObject(json);
                result.count = RequireInteger(fields, "count", 0);
                records = BoundedRecords(Require(fields, "results"), 1000);
                result.next = NullableString(fields, "next", 2048);
                if (result.count > 10000 || records.Count > result.count || (result.next != null && (result.next.Length == 0 || records.Count == 0)))
                    throw new FormatException("The inventory pagination was invalid.");
            }
            result.results = new InventoryEntryDto[records.Count];
            var ids = new HashSet<int>();
            var itemIds = new HashSet<int>();
            for (int index = 0; index < records.Count; index++)
            {
                var row = ReadObject(records[index]);
                if (!ids.Add(RequireInteger(row, "id", 1))) throw new FormatException("The inventory contains duplicate rows.");
                RequireInteger(row, "quantity", 0);
                RequiredDate(row, "updated_at");
                var item = ReadObject(Require(row, "item"));
                if (!itemIds.Add(RequireInteger(item, "id", 1))) throw new FormatException("The inventory contains duplicate items.");
                BoundedString(item, "name", 200, true);
                BoundedString(item, "description", 16384);
                BoundedString(item, "icon", 100);
                BoundedString(item, "sprite_key", 100);
                BoundedString(item, "item_type", 100, true);
                NullableString(item, "food_species_name", 100);
                var entry = JsonUtility.FromJson<InventoryEntryDto>(records[index]);
                entry.item.food_species_name = NullableString(item, "food_species_name", 100);
                entry.item.pet_species_name = NullableString(item, "pet_species_name", 100);
                entry.item.potion_type_name = NullableString(item, "potion_type_name", 100);
                result.results[index] = entry;
            }
            return result;
        }

        private static void ValidateOwnedCreature(Dictionary<string, string> fields)
        {
            RequireBoolean(fields, "is_active");
            RequiredDate(fields, "created_at");
            RequiredDate(fields, "updated_at");
            var species = ReadObject(Require(fields, "species"));
            RequireInteger(species, "id", 1);
            BoundedString(species, "name", 100, true);
            BoundedString(species, "icon", 64);
            BoundedString(species, "sprite_key", 100);
            BoundedString(species, "description", 16384);
            BoundedString(species, "food_preference", 100);
            var potion = ReadObject(Require(fields, "potion"));
            RequireInteger(potion, "id", 1);
            NullableString(potion, "slug", 100);
            BoundedString(potion, "name", 100, true);
            BoundedString(potion, "sprite_key", 100);
            BoundedString(potion, "description", 16384);
            BoundedString(potion, "rarity", 40, true);
            string color = BoundedString(potion, "color_hex", 7, true);
            if (color.Length != 7 || color[0] != '#') throw new FormatException("The potion color is invalid.");
            for (int index = 1; index < color.Length; index++)
                if (!Uri.IsHexDigit(color[index])) throw new FormatException("The potion color is invalid.");
        }

        private static List<string> BoundedRecords(string json, int maximum)
        {
            var records = ReadArray(json);
            if (records.Count > maximum) throw new FormatException("The server returned too many records.");
            return records;
        }

        private static string BoundedString(Dictionary<string, string> fields, string name, int maximum, bool nonempty = false)
        {
            RequireString(fields, name);
            string value = JsonUtility.FromJson<StringPayload>("{\"value\":" + Require(fields, name) + "}").value;
            if (value == null || value.Length > maximum || (nonempty && string.IsNullOrWhiteSpace(value)))
                throw new FormatException("The server returned an invalid '" + name + "'.");
            return value;
        }

        private static string NullableString(Dictionary<string, string> fields, string name, int maximum)
        {
            return Require(fields, name) == "null" ? null : BoundedString(fields, name, maximum);
        }

        private static string RequiredDate(Dictionary<string, string> fields, string name)
        {
            string value = BoundedString(fields, name, 100, true);
            if (!DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.None, out _))
                throw new FormatException("The server returned an invalid '" + name + "'.");
            return value;
        }

        private static string NullableDate(Dictionary<string, string> fields, string name)
        {
            return Require(fields, name) == "null" ? null : RequiredDate(fields, name);
        }

        public static HabitPageDto ParseHabitPage(string json)
        {
            var fields = ReadObject(json);
            int count = RequireInteger(fields, "count", 0);
            string next = Require(fields, "next");
            if (next != "null" && !next.StartsWith("\"", StringComparison.Ordinal))
                throw new FormatException("The habit pagination link was invalid.");
            var records = ReadArray(Require(fields, "results"));
            var page = JsonUtility.FromJson<HabitPageDto>(json);
            // JsonUtility materializes JSON null strings as empty strings. Keep
            // the API's explicit end-of-pagination marker as a null reference.
            page.next = next == "null" ? null : JsonUtility.FromJson<StringPayload>("{\"value\":" + next + "}").value;
            page.results = new HabitDto[records.Count];
            page.count = count;
            for (int index = 0; index < records.Count; index++)
                page.results[index] = ParseHabit(records[index]);
            return page;
        }

        public static HabitDto ParseHabit(string json)
        {
            var fields = ReadObject(json);
            RequireInteger(fields, "id", 1);
            RequireInteger(fields, "user", 1);
            RequireInteger(fields, "xp_reward", 0);
            RequireInteger(fields, "max_taps_per_day", 0);
            RequireInteger(fields, "taps_today", 0);
            RequireInteger(fields, "strength", int.MinValue);
            RequireBoolean(fields, "is_active");
            RequireBoolean(fields, "pending_parent_review");
            RequireString(fields, "name");
            RequireString(fields, "habit_type");
            var habit = JsonUtility.FromJson<HabitDto>(json);
            if (string.IsNullOrWhiteSpace(habit.name) ||
                (habit.habit_type != "positive" && habit.habit_type != "negative" && habit.habit_type != "both"))
                throw new FormatException("The server returned an incomplete habit.");
            return habit;
        }

        public static HabitTapDto ParseHabitTap(string json)
        {
            var fields = ReadObject(json);
            if (RequireInteger(fields, "direction", int.MinValue) != 1)
                throw new FormatException("The server did not confirm a positive habit tap.");
            RequireInteger(fields, "xp_reward", 0);
            RequireInteger(fields, "new_strength", int.MinValue);
            // game_event may be null when an optional game-loop step fails.
            // The base tap still succeeded and must not be replayed.
            var tap = JsonUtility.FromJson<HabitTapDto>(json);
            if (!fields.TryGetValue("game_event", out var eventJson) || eventJson == "null")
                tap.game_event = null;
            else
            {
                var eventFields = ReadObject(eventJson);
                if (IsMissingOrNull(eventFields, "streak")) tap.game_event.streak = null;
                if (IsMissingOrNull(eventFields, "quest")) tap.game_event.quest = null;
                if (IsMissingOrNull(eventFields, "daily_challenge")) tap.game_event.daily_challenge = null;
                if (IsMissingOrNull(eventFields, "drops")) tap.game_event.drops = null;
                if (IsMissingOrNull(eventFields, "notifications")) tap.game_event.notifications = null;
            }
            return tap;
        }

        private static bool IsMissingOrNull(Dictionary<string, string> fields, string name)
        {
            return !fields.TryGetValue(name, out var value) || value == "null";
        }

        public static MeadowDto ParseMeadow(string json)
        {
            var fields = ReadObject(json);
            if (RequireInteger(fields, "schema_version", 1) != 1)
                throw new FormatException("This meadow response needs a newer version of your world.");
            int count = RequireInteger(fields, "keepsake_count", 0);
            RequireInteger(fields, "journal_xp_awarded", 0);
            var records = ReadArray(Require(fields, "keepsakes"));
            if (records.Count > 30 || records.Count > count)
                throw new FormatException("The meadow returned an invalid keepsake collection.");
            var result = JsonUtility.FromJson<MeadowDto>(json);
            result.keepsakes = new KeepsakeDto[records.Count];
            var ids = new HashSet<string>(StringComparer.Ordinal);
            for (var index = 0; index < records.Count; index++)
            {
                var itemFields = ReadObject(records[index]);
                foreach (var key in new[] { "receipt_id", "type", "title", "earned_at" }) RequireString(itemFields, key);
                var item = JsonUtility.FromJson<KeepsakeDto>(records[index]);
                if (item.receipt_id == null || !item.receipt_id.StartsWith("journal:", StringComparison.Ordinal)
                    || !int.TryParse(item.receipt_id.Substring(8), NumberStyles.None, CultureInfo.InvariantCulture, out var entryId) || entryId < 1
                    || !ids.Add(item.receipt_id) || item.type != "memory_bloom" || item.title != "Memory bloom"
                    || !DateTimeOffset.TryParse(item.earned_at, CultureInfo.InvariantCulture, DateTimeStyles.None, out _))
                    throw new FormatException("The meadow returned an incomplete keepsake.");
                result.keepsakes[index] = item;
            }
            return result;
        }

        public static ApiError HttpError(long status, string body, bool mutation, bool transportFailure)
        {
            string message = null;
            try
            {
                ReadObject(body);
                var payload = JsonUtility.FromJson<ErrorPayload>(body);
                message = string.IsNullOrWhiteSpace(payload.error) ? payload.detail : payload.error;
            }
            catch (Exception) { /* HTML proxy responses are not user-facing diagnostics. */ }
            if (string.IsNullOrWhiteSpace(message))
            {
                if (status == 401) message = "Your session has expired. Sign in again.";
                else if (status == 403) message = "This account cannot perform that action.";
                else if (status == 429) message = "The server is receiving too many requests. Wait before trying again.";
                else if (transportFailure) message = "Could not reach the server. Check the server address and connection.";
                else message = "The server could not complete the request (HTTP " + status + ").";
            }
            message = message.Replace('\r', ' ').Replace('\n', ' ');
            if (message.Length > 400) message = message.Substring(0, 400);
            bool unknown = mutation && (transportFailure || status == 408 || status >= 500 || (status >= 300 && status < 400));
            if (unknown) message += " The action may have been saved. Refresh and review its state before trying again.";
            return new ApiError(message, status, unknown, status == 401);
        }

        private static string Require(Dictionary<string, string> fields, string name)
        {
            if (!fields.TryGetValue(name, out var value))
                throw new FormatException("The server response is missing '" + name + "'.");
            return value;
        }

        private static int RequireInteger(Dictionary<string, string> fields, string name, int minimum)
        {
            if (!int.TryParse(Require(fields, name), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out int value) || value < minimum)
                throw new FormatException("The server returned an invalid '" + name + "'.");
            return value;
        }

        private static void RequireBoolean(Dictionary<string, string> fields, string name)
        {
            string value = Require(fields, name);
            if (value != "true" && value != "false")
                throw new FormatException("The server returned an invalid '" + name + "'.");
        }

        private static void RequireString(Dictionary<string, string> fields, string name)
        {
            if (!Require(fields, name).StartsWith("\"", StringComparison.Ordinal))
                throw new FormatException("The server returned an invalid '" + name + "'.");
        }

        // JsonUtility ignores unknown/missing fields. This scanner only preserves
        // each top-level JSON value for presence/type checks; DTO deserialization
        // remains JsonUtility's responsibility. It handles escaped/nested strings,
        // rather than searching for field-name substrings in untrusted JSON.
        private static Dictionary<string, string> ReadObject(string json)
        {
            if (string.IsNullOrWhiteSpace(json) || json.Length > 2 * 1024 * 1024)
                throw new FormatException("The server returned an empty or oversized response.");
            var values = new Dictionary<string, string>(StringComparer.Ordinal);
            int index = 0;
            Eat(json, ref index, '{');
            SkipWhitespace(json, ref index);
            if (Peek(json, index) != '}')
            {
                while (true)
                {
                    int start = index;
                    SkipString(json, ref index);
                    string key = JsonUtility.FromJson<StringPayload>("{\"value\":" + json.Substring(start, index - start) + "}").value;
                    Eat(json, ref index, ':');
                    SkipWhitespace(json, ref index);
                    start = index;
                    SkipValue(json, ref index, 0);
                    if (values.ContainsKey(key)) throw new FormatException("The server returned duplicate JSON fields.");
                    values.Add(key, json.Substring(start, index - start).Trim());
                    SkipWhitespace(json, ref index);
                    if (Peek(json, index) == '}') break;
                    Eat(json, ref index, ',');
                    SkipWhitespace(json, ref index);
                }
            }
            Eat(json, ref index, '}');
            SkipWhitespace(json, ref index);
            if (index != json.Length) throw new FormatException("Unexpected data after the server response.");
            return values;
        }

        private static List<string> ReadArray(string json)
        {
            if (string.IsNullOrWhiteSpace(json) || json.Length > 2 * 1024 * 1024)
                throw new FormatException("The server returned an empty or oversized response.");
            var values = new List<string>();
            int index = 0;
            Eat(json, ref index, '[');
            SkipWhitespace(json, ref index);
            if (Peek(json, index) != ']')
            {
                while (true)
                {
                    int start = index;
                    SkipValue(json, ref index, 0);
                    values.Add(json.Substring(start, index - start));
                    SkipWhitespace(json, ref index);
                    if (Peek(json, index) == ']') break;
                    Eat(json, ref index, ',');
                    SkipWhitespace(json, ref index);
                }
            }
            Eat(json, ref index, ']');
            SkipWhitespace(json, ref index);
            if (index != json.Length) throw new FormatException("Invalid array in the server response.");
            return values;
        }

        private static void SkipValue(string json, ref int index, int depth)
        {
            if (depth > 64) throw new FormatException("The server response is nested too deeply.");
            SkipWhitespace(json, ref index);
            char first = Peek(json, index);
            if (first == '\"') { SkipString(json, ref index); return; }
            if (first == '{' || first == '[')
            {
                char end = first == '{' ? '}' : ']';
                index++;
                SkipWhitespace(json, ref index);
                if (Peek(json, index) != end)
                {
                    while (true)
                    {
                        if (first == '{') { SkipString(json, ref index); Eat(json, ref index, ':'); }
                        SkipValue(json, ref index, depth + 1);
                        SkipWhitespace(json, ref index);
                        if (Peek(json, index) == end) break;
                        Eat(json, ref index, ',');
                        SkipWhitespace(json, ref index);
                    }
                }
                Eat(json, ref index, end);
                return;
            }
            int start = index;
            while (index < json.Length && !char.IsWhiteSpace(json[index]) && json[index] != ',' && json[index] != '}' && json[index] != ']') index++;
            string primitive = json.Substring(start, index - start);
            if (primitive != "true" && primitive != "false" && primitive != "null" &&
                !double.TryParse(primitive, NumberStyles.Float, CultureInfo.InvariantCulture, out _))
                throw new FormatException("The server returned invalid JSON.");
        }

        private static void SkipString(string json, ref int index)
        {
            SkipWhitespace(json, ref index);
            if (Peek(json, index++) != '\"') throw new FormatException("The server returned invalid JSON text.");
            while (index < json.Length)
            {
                char character = json[index++];
                if (character == '\"') return;
                if (character < ' ') throw new FormatException("The server returned an invalid JSON string.");
                if (character != '\\') continue;
                char escaped = Peek(json, index++);
                if (escaped == 'u')
                {
                    for (int digit = 0; digit < 4; digit++)
                        if (!Uri.IsHexDigit(Peek(json, index++))) throw new FormatException("Invalid JSON Unicode escape.");
                }
                else if ("\"\\/bfnrt".IndexOf(escaped) < 0) throw new FormatException("Invalid JSON escape.");
            }
            throw new FormatException("The server returned an unterminated JSON string.");
        }

        private static char Peek(string json, int index)
        {
            if (index >= json.Length) throw new FormatException("The server response was truncated.");
            return json[index];
        }

        private static void Eat(string json, ref int index, char expected)
        {
            SkipWhitespace(json, ref index);
            if (Peek(json, index++) != expected) throw new FormatException("The server returned invalid JSON.");
        }

        private static void SkipWhitespace(string json, ref int index)
        {
            while (index < json.Length && char.IsWhiteSpace(json[index])) index++;
        }
    }
}
