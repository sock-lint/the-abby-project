using AbbyCamp.Data;

namespace AbbyCamp.Presentation
{
    public enum OwnedCompanionKind { None, Pet, Mount }

    /// <summary>A presentation of a confirmed owned row, never an ownership grant.</summary>
    public sealed class OwnedCompanionChoice
    {
        public static readonly OwnedCompanionChoice None = new OwnedCompanionChoice(OwnedCompanionKind.None, 0, null, null, "", 0, false);
        public readonly OwnedCompanionKind Kind;
        public readonly int CreatureId;
        public readonly SpeciesDto Species;
        public readonly PotionDto Potion;
        public readonly string DisplayName;
        public readonly int Growth;
        public readonly bool IsEvolved;

        private OwnedCompanionChoice(OwnedCompanionKind kind, int id, SpeciesDto species, PotionDto potion, string name, int growth, bool evolved)
        {
            Kind = kind; CreatureId = id; Species = species; Potion = potion;
            DisplayName = name; Growth = growth; IsEvolved = evolved;
        }

        public static OwnedCompanionChoice FromPet(OwnedPetDto pet) => pet == null || pet.id <= 0 || pet.species == null || pet.potion == null
            ? None : new OwnedCompanionChoice(OwnedCompanionKind.Pet, pet.id, pet.species, pet.potion,
                string.IsNullOrWhiteSpace(pet.name) ? pet.species.name : pet.name, pet.growth_points, pet.evolved_to_mount);

        public static OwnedCompanionChoice FromMount(OwnedMountDto mount) => mount == null || mount.id <= 0 || mount.species == null || mount.potion == null
            ? None : new OwnedCompanionChoice(OwnedCompanionKind.Mount, mount.id, mount.species, mount.potion,
                mount.DisplayName, 100, true);

        public OwnedCompanionChoice WithConfirmedFeed(int petId, PetFeedDto receipt)
        {
            if (Kind != OwnedCompanionKind.Pet || CreatureId != petId || receipt == null) return this;
            return new OwnedCompanionChoice(Kind, CreatureId, Species, Potion, DisplayName, receipt.new_growth, IsEvolved || receipt.evolved);
        }
    }

    /// <summary>Deterministic choice from server state plus an acknowledged local selection.</summary>
    public static class OwnedCompanionResolver
    {
        public static OwnedCompanionChoice Resolve(StableDto stable, OwnedCompanionKind preferredKind = OwnedCompanionKind.None, int preferredId = 0)
        {
            if (stable == null) return OwnedCompanionChoice.None;
            // Pet and mount active flags are independent. An explicit saved
            // choice resolves that ambiguity, but only while its row is active.
            if (preferredKind == OwnedCompanionKind.Pet && stable.pets != null)
                foreach (var pet in stable.pets)
                    if (pet != null && pet.id == preferredId && pet.is_active) return OwnedCompanionChoice.FromPet(pet);
            if (preferredKind == OwnedCompanionKind.Mount && stable.mounts != null)
                foreach (var mount in stable.mounts)
                    if (mount != null && mount.id == preferredId && mount.is_active) return OwnedCompanionChoice.FromMount(mount);

            if (stable.pets != null)
            {
                foreach (var pet in stable.pets)
                    if (pet != null && pet.is_active && !pet.evolved_to_mount) return OwnedCompanionChoice.FromPet(pet);
                // Django preserves the selected pet and its active flag at
                // evolution; displaying its grown form does not activate a mount.
                foreach (var pet in stable.pets)
                    if (pet != null && pet.is_active && pet.evolved_to_mount) return OwnedCompanionChoice.FromPet(pet);
            }
            if (stable.mounts != null)
                foreach (var mount in stable.mounts)
                    if (mount != null && mount.is_active) return OwnedCompanionChoice.FromMount(mount);
            return OwnedCompanionChoice.None;
        }
    }
}
