using System;
using AbbyCamp.Presentation;
using AbbyCamp.UI;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine.SceneManagement;

namespace AbbyCamp.Editor
{
    /// <summary>Adds exact owned models to a transient build scene without changing private inputs.</summary>
    public sealed class LicensedCreatureBuildBindings : IProcessSceneWithReport
    {
        public int callbackOrder => 0;

        public static OwnedCreatureVisualBinding[] ResolveEffectiveBindings(CampPresentationDefinition presentation)
        {
            if (presentation == null) throw new InvalidOperationException("The licensed Meadow presentation is missing.");
            if (presentation.OwnedCreatureAppearances != null && presentation.OwnedCreatureAppearances.Length > 0)
                return presentation.OwnedCreatureAppearances;
            // These definitions were prepared and validated by the original
            // licensed pipeline before owned binding metadata was introduced.
            return new[]
            {
                new OwnedCreatureVisualBinding
                {
                    SpeciesSpriteKey = "cute-chick", PotionSlug = "base",
                    Companion = AssetDatabase.LoadAssetAtPath<VisualDefinition>(MeshtintSetup.GeneratedPath + "/chick.asset"),
                    Evolved = AssetDatabase.LoadAssetAtPath<VisualDefinition>(MeshtintSetup.GeneratedPath + "/bird.asset"),
                },
            };
        }

        public void OnProcessScene(Scene scene, BuildReport report)
        {
            // This callback can also run for Editor play mode. Only compiled
            // licensed builds receive references; saved scenes are never written.
            if (report == null || !string.Equals(scene.path, MeshtintSetup.ScenePath, StringComparison.Ordinal)) return;
            foreach (var root in scene.GetRootGameObjects())
                foreach (var controller in root.GetComponentsInChildren<CampPrototypeController>(true))
                    controller.ConfigureBuildCreatureAppearances(ResolveEffectiveBindings(controller.WorldPresentation));
        }
    }
}
