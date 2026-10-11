using System;

namespace AbbyCamp.Data
{
    // Deliberately small projections of the existing Django serializers. Content IDs,
    // rather than any model or animation names, cross the presentation boundary.
    [Serializable]
    public sealed class UserDto
    {
        public int id;
        public string username;
        public string display_name;
        public string role;
        public FamilyDto family;

        public string DisplayName => string.IsNullOrWhiteSpace(display_name) ? username : display_name;
    }

    [Serializable]
    public sealed class FamilyDto
    {
        public int id;
        public string name;
        public string timezone;
    }

    [Serializable]
    public sealed class HabitDto
    {
        public int id;
        public string name;
        public string habit_type;
        public int user;
        public int xp_reward;
        public int max_taps_per_day;
        public int taps_today;
        public int strength;
        public bool is_active;
        public bool pending_parent_review;
        public HabitSkillTagDto[] skill_tags;

        public bool SupportsPositiveTap => habit_type == "positive" || habit_type == "both";
        public bool DailyLimitReached => taps_today >= max_taps_per_day;

        public bool IsEligibleForUser(int userId)
        {
            return id > 0 && user == userId && is_active && !pending_parent_review && SupportsPositiveTap;
        }
    }

    [Serializable]
    public sealed class HabitSkillTagDto
    {
        public int skill;
        public string skill_name;
        public int xp_weight;
    }

    [Serializable]
    public sealed class HabitPageDto
    {
        public int count;
        public string next;
        public HabitDto[] results;
    }

    [Serializable]
    public sealed class CharacterDto
    {
        public int id;
        public string username;
        public string display_name;
        public int level;
        public int login_streak;
        public int longest_login_streak;
        public int perfect_days_count;
        public string last_active_date;
    }

    // Fixed internal destinations. Neither notification content nor API
    // pagination links can supply an arbitrary browser navigation target.
    public enum PlayDestination
    {
        Today, Journal, Grades, Tasks, RewardShop, Satchel,
        Bestiary, BestiaryHatchery, BestiaryCompanions, BestiaryMounts, BestiaryCodex,
        TasksStudy, TasksDuties, TasksRituals, TasksMovement, TasksVentures, TasksForge, TasksTrials,
        Skills, Badges, Lorebook, Character, Yearbook, Creations, Wages, Coffers, Savings
    }

    [Serializable]
    public sealed class CoinBalanceDto
    {
        public int balance;
        public CoinTransactionDto[] recent_transactions;
    }

    [Serializable]
    public sealed class CoinTransactionDto
    {
        public int id;
        public int user;
        public int amount;
        public string reason;
        public string description;
        public string created_at;
    }

    [Serializable]
    public sealed class DropDto
    {
        public int id;
        public int item;
        public string item_name;
        public string item_icon;
        public string item_sprite_key;
        public string item_rarity;
        public string trigger_type;
        public int quantity;
        public bool was_salvaged;
        public string created_at;
    }

    [Serializable]
    public sealed class NotificationDto
    {
        public int id;
        public string title;
        public string message;
        public string notification_type;
        public bool is_read;
        public string created_at;
        public string link;
    }

    [Serializable]
    public sealed class NotificationPageDto
    {
        public int count;
        public string next;
        public NotificationDto[] results;
    }

    [Serializable]
    public sealed class UnreadCountDto { public int count; }

    [Serializable]
    public sealed class SpeciesDto
    {
        public int id;
        public string name;
        public string icon;
        public string sprite_key;
        public string description;
        public string food_preference;
    }

    [Serializable]
    public sealed class PotionDto
    {
        public int id;
        public string slug;
        public string name;
        public string sprite_key;
        public string color_hex;
        public string rarity;
        public string description;
    }

    [Serializable]
    public sealed class OwnedPetDto
    {
        public int id;
        public SpeciesDto species;
        public PotionDto potion;
        public string name;
        public int growth_points;
        public bool is_active;
        public bool evolved_to_mount;
        public bool is_fully_grown;
        public string happiness_level;
        public string last_fed_at;
        public string created_at;
        public string updated_at;

        public string DisplayName => string.IsNullOrWhiteSpace(name) ? potion.name + " " + species.name : name;
    }

    [Serializable]
    public sealed class OwnedMountDto
    {
        public int id;
        public SpeciesDto species;
        public PotionDto potion;
        public bool is_active;
        public string last_bred_at;
        public MountExpeditionDto active_expedition;
        public string created_at;
        public string updated_at;

        public string DisplayName => potion.name + " " + species.name;
    }

    [Serializable]
    public sealed class MountExpeditionDto
    {
        public int id;
        public int mount_id;
        public string status;
        public bool is_ready;
        public int seconds_remaining;
    }

    [Serializable]
    public sealed class InventoryItemDto
    {
        public int id;
        public string name;
        public string description;
        public string icon;
        public string sprite_key;
        public string item_type;
        public string food_species_name;
    }

    [Serializable]
    public sealed class InventoryEntryDto
    {
        public int id;
        public InventoryItemDto item;
        public int quantity;
        public string updated_at;
    }

    [Serializable]
    public sealed class InventoryPageDto
    {
        public int count;
        public string next;
        public InventoryEntryDto[] results;
    }

    [Serializable]
    public sealed class PetFeedDto
    {
        // growth_added is the server's configured feed amount; new_growth is
        // the confirmed total after the evolution threshold has clamped it.
        public int growth_added;
        public int new_growth;
        public bool evolved;
        public int mount_id;
    }

    [Serializable]
    public sealed class StableDto
    {
        public OwnedPetDto[] pets;
        public OwnedMountDto[] mounts;
        public int total_pets;
        public int total_mounts;
        public int total_possible;

        public OwnedPetDto ActiveCompanion
        {
            get
            {
                if (pets != null)
                    foreach (var pet in pets)
                        if (pet.is_active && !pet.evolved_to_mount) return pet;
                return null;
            }
        }

        public OwnedMountDto ActiveMount
        {
            get
            {
                if (mounts != null)
                    foreach (var mount in mounts)
                        if (mount.is_active) return mount;
                return null;
            }
        }
    }

    [Serializable]
    public sealed class HabitTapDto
    {
        public int direction;
        // This is the configured skill XP pool. Without skill tags the backend
        // distributes no skill XP; it is not a character XP total or coin award.
        public int xp_reward;
        public int new_strength;
        public GameEventDto game_event;

        public string DescribeConfirmedOutcome(HabitDto habit = null)
        {
            // The base tap is committed before the optional game loop. That
            // pipeline can roll back a step after populating its result object,
            // so game_event alone cannot confirm ledger, inventory, or quest
            // rewards. Keep those DTOs for future authoritative-state reads.
            // xp_reward likewise describes a pool rather than exact XP granted.
            return "Ritual recorded. Strength: " + new_strength + ".";
        }
    }

    [Serializable]
    public sealed class GameEventDto
    {
        public string trigger_type;
        public StreakEventDto streak;
        public DropEventDto[] drops;
        public QuestEventDto quest;
        public DailyChallengeEventDto daily_challenge;
        public string[] notifications;
    }

    [Serializable]
    public sealed class StreakEventDto
    {
        public bool is_first_today;
        public int check_in_bonus_coins;
        public int streak;
        public float multiplier;
        public bool freeze_consumed;
        public bool streak_broken;
    }

    [Serializable]
    public sealed class DropEventDto
    {
        public int item_id;
        public string item_name;
        public string item_type;
        public string item_rarity;
        public int quantity;
        public bool was_salvaged;
    }

    [Serializable]
    public sealed class QuestEventDto
    {
        public int quest_id;
        public string quest_name;
        public int damage_dealt;
        public int new_progress;
        public int target;
        public bool completed;
    }

    [Serializable]
    public sealed class DailyChallengeEventDto
    {
        public int challenge_id;
        public string challenge_type;
        public int progress;
        public int target;
        public bool newly_completed;
    }

    [Serializable]
    public sealed class MeadowDto
    {
        public int schema_version;
        public int keepsake_count;
        public int journal_xp_awarded;
        public KeepsakeDto[] keepsakes;
    }

    [Serializable]
    public sealed class KeepsakeDto
    {
        public string receipt_id;
        public string type;
        public string title;
        public string earned_at;
    }

    public sealed class ApiError
    {
        public readonly string Message;
        public readonly long StatusCode;
        // True means an action may have reached Django. Refresh server state
        // and ask the user to reconcile it; never replay that POST automatically.
        public readonly bool OutcomeUnknown;
        public readonly bool RequiresLogin;

        public ApiError(string message, long statusCode = 0, bool outcomeUnknown = false, bool requiresLogin = false)
        {
            Message = message;
            StatusCode = statusCode;
            OutcomeUnknown = outcomeUnknown;
            RequiresLogin = requiresLogin;
        }

        public override string ToString() => Message;
    }
}
