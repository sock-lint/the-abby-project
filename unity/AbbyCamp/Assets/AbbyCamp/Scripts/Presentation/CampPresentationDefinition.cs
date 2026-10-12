using System;
using UnityEngine;

namespace AbbyCamp.Presentation
{
    [Serializable]
    public sealed class OwnedCreatureVisualBinding
    {
        public string SpeciesSpriteKey;
        public string PotionSlug;
        public VisualDefinition Companion;
        public VisualDefinition Evolved;

        public static bool TryResolve(OwnedCreatureVisualBinding[] bindings, string speciesSpriteKey, string potionSlug,
            bool evolved, out VisualDefinition definition)
        {
            definition = null;
            if (string.IsNullOrEmpty(speciesSpriteKey) || string.IsNullOrEmpty(potionSlug) || bindings == null) return false;
            foreach (var binding in bindings)
            {
                if (binding == null || !string.Equals(binding.SpeciesSpriteKey, speciesSpriteKey, StringComparison.Ordinal)
                    || !string.Equals(binding.PotionSlug, potionSlug, StringComparison.Ordinal)) continue;
                var candidate = evolved ? binding.Evolved : binding.Companion;
                // Missing models are still previews, even if a portrait exists.
                if (candidate == null || candidate.ModelPrefab == null) return false;
                definition = candidate;
                return true;
            }
            return false;
        }
    }

    /// <summary>Authored appearance and palette settings, independent of saved progress.</summary>
    [CreateAssetMenu(menuName = "Abby Camp/World Presentation")]
    public sealed class CampPresentationDefinition : ScriptableObject
    {
        public string WorldTitle = "MEMORY MEADOW";
        public VisualDefinition PlayerAppearance;
        public VisualDefinition CompanionAppearance;
        public VisualDefinition AlternateCompanionAppearance;
        [Tooltip("Exact server species sprite key and potion slug. Empty in the public preview.")]
        public OwnedCreatureVisualBinding[] OwnedCreatureAppearances = Array.Empty<OwnedCreatureVisualBinding>();
        public Sprite MemoryBloom;
        public Font UiFont;
        public Color Paper = new Color(1f, .972549f, .933333f);
        public Color Ink = new Color(.286275f, .219608f, .309804f);
        public Color Primary = new Color(.458824f, .376471f, .658824f);
        public Color Grass = new Color(.662745f, .811765f, .662745f);
        public Color GrassEdge = new Color(.55f, .69f, .55f);
        public Color Path = new Color(1f, .847059f, .572549f);
        public Color Accent = new Color(.956863f, .713725f, .627451f);
        public Color Sky = new Color(.862745f, .933333f, .956863f);

        public bool TryResolveOwnedAppearance(string speciesSpriteKey, string potionSlug, bool evolved, out VisualDefinition definition)
        {
            return OwnedCreatureVisualBinding.TryResolve(OwnedCreatureAppearances, speciesSpriteKey, potionSlug, evolved, out definition);
        }
    }
}
