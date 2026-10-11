using System;
using System.IO;
using System.Linq;
using AbbyCamp.Presentation;
using AbbyCamp.World;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;

namespace AbbyCamp.Editor
{
    /// <summary>Local licensed appearance layer; public source contains no purchased art.</summary>
    public static class MeshtintSetup
    {
        public const string SourcePath = "Assets/ThirdParty/Meshtint";
        public const string GeneratedPath = "Assets/AbbyCamp/Licensed";
        public const string ScenePath = GeneratedPath + "/MemoryMeadow.unity";
        public const string PresentationPath = GeneratedPath + "/Meadow.asset";
        private const string ForestPath = SourcePath + "/Forest Ruins Pack Cute Series/Prefabs/";
        private const string ArcherPath = SourcePath + "/Female Archer Pack 01 Cute Series/";

        [MenuItem("Abby Camp/Licensed Cute Series/Prepare meadow")]
        public static void Prepare()
        {
            if (!Directory.Exists(SourcePath))
                throw new InvalidOperationException("First run python scripts/unity/stage_meshtint.py with the purchased ZIPs.");
            Directory.CreateDirectory(GeneratedPath);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            ConfigureMaterialsAndTextures();
            var basePresentation = AssetDatabase.LoadAssetAtPath<CampPresentationDefinition>(CampSceneBuilder.PresentationPath);
            if (basePresentation == null) throw new InvalidOperationException("The public Meadow presentation is missing.");
            var settings = AssetDatabase.LoadAssetAtPath<CampPresentationDefinition>(PresentationPath);
            if (settings == null)
            {
                settings = UnityEngine.Object.Instantiate(basePresentation);
                AssetDatabase.CreateAsset(settings, PresentationPath);
            }
            // Palette/font/receipts stay shared. These definitions only replace appearance.
            var chick = CreateCreature("Chick", "Idle", "Jump Forward In Place", .9f, 0f);
            var fledgling = CreateCreature("Fledgling", "Idle", "Walk Forward In Place", 1.05f, 0f);
            CreateCreature("Bird", "Fly Idle", "Fly Forward In Place", 1.3f, .3f);
            settings.CompanionAppearance = chick;
            // Appearance preview demonstrates swaps; it is not an earned evolution.
            settings.AlternateCompanionAppearance = fledgling;
            if (Directory.Exists(ArcherPath)) settings.PlayerAppearance = CreateArcher();
            EditorUtility.SetDirty(settings);
            AssetDatabase.SaveAssets();
            CampSceneBuilder.BuildScene(settings, ScenePath, DecorateForest);
            Validate();
            Debug.Log("ABBY_MESHTINT_PREPARED: licensed companion, stage definitions, avatar, forest and shared portraits.");
        }

        private static void ConfigureMaterialsAndTextures()
        {
            var shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null) throw new InvalidOperationException("URP Lit shader is missing.");
            foreach (var guid in AssetDatabase.FindAssets("t:Material", new[] { SourcePath }))
            {
                var material = AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(guid));
                var texture = material.HasProperty("_BaseMap") && material.GetTexture("_BaseMap") != null
                    ? material.GetTexture("_BaseMap") : material.mainTexture;
                if (new[] { "Chick", "Fledgling", "Bird", "Forest Ruins" }.Contains(material.name) && texture == null)
                    throw new InvalidOperationException("Missing supplied texture for " + material.name + "; restage the complete pack including PSD textures.");
                var color = material.HasProperty("_BaseColor") ? material.GetColor("_BaseColor") : material.color;
                var cutout = (material.HasProperty("_Mode") && Mathf.Approximately(material.GetFloat("_Mode"), 1f))
                    || (material.HasProperty("_AlphaClip") && material.GetFloat("_AlphaClip") > .5f)
                    || material.IsKeywordEnabled("_ALPHATEST_ON");
                material.shader = shader;
                material.SetTexture("_BaseMap", texture);
                material.SetColor("_BaseColor", color);
                material.SetFloat("_Smoothness", .05f);
                material.SetFloat("_Metallic", 0f);
                material.SetFloat("_AlphaClip", cutout ? 1f : 0f);
                if (cutout) material.EnableKeyword("_ALPHATEST_ON");
                else material.DisableKeyword("_ALPHATEST_ON");
                if (material.name.Contains("Leaves")) material.SetFloat("_Cull", 0f);
                EditorUtility.SetDirty(material);
            }
            foreach (var root in new[] { SourcePath, GeneratedPath + "/Art" })
            {
                if (!Directory.Exists(root)) continue;
                foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { root }))
                {
                    var importer = AssetImporter.GetAtPath(AssetDatabase.GUIDToAssetPath(guid)) as TextureImporter;
                    if (importer == null) continue;
                    importer.maxTextureSize = 512;
                    if (root.EndsWith("/Art", StringComparison.Ordinal))
                    {
                        importer.textureType = TextureImporterType.Sprite;
                        importer.spriteImportMode = SpriteImportMode.Single;
                        importer.alphaIsTransparency = true;
                        importer.mipmapEnabled = false;
                    }
                    importer.SaveAndReimport();
                }
            }
            AssetDatabase.SaveAssets();
        }

        private static VisualDefinition CreateCreature(string family, string idle, string movement, float height, float lift)
        {
            var folder = SourcePath + "/" + family + " Cute Series/";
            var source = AssetDatabase.LoadAssetAtPath<GameObject>(folder + "Prefabs/" + family + ".prefab");
            if (source == null) throw new InvalidOperationException("Missing purchased " + family + " prefab.");
            var controller = CreateController(family.ToLowerInvariant(), Clip(folder + "FBX/" + family + "@" + idle + ".FBX"),
                Clip(folder + "FBX/" + family + "@" + movement + ".FBX"));
            var definition = CreateVisual(family.ToLowerInvariant(), source, controller, height, lift, false);
            definition.Portrait = AssetDatabase.LoadAssetAtPath<Sprite>(GeneratedPath + "/Art/" + family.ToLowerInvariant() + ".png");
            EditorUtility.SetDirty(definition);
            return definition;
        }

        private static VisualDefinition CreateArcher()
        {
            var source = AssetDatabase.LoadAssetAtPath<GameObject>(ArcherPath + "02 Customized Sample Prefabs/Female Archer 01.prefab");
            if (source == null) throw new InvalidOperationException("Missing purchased Female Archer sample prefab.");
            var animationPath = ArcherPath + "Standard Assets Files/Animators and Animations/";
            var controller = CreateController("explorer", Clip(animationPath + "Char@Idle.FBX"), Clip(animationPath + "Char@Walk Forward In Place.FBX"));
            return CreateVisual("explorer", source, controller, 1.6f, 0f, true);
        }

        private static AnimationClip Clip(string path)
        {
            var importer = AssetImporter.GetAtPath(path) as ModelImporter;
            if (importer == null) throw new InvalidOperationException("Missing movement source: " + path);
            var clips = importer.clipAnimations.Length > 0 ? importer.clipAnimations : importer.defaultClipAnimations;
            foreach (var clip in clips)
            {
                clip.loopTime = true;
                clip.lockRootRotation = true;
                clip.lockRootHeightY = true;
                clip.lockRootPositionXZ = true;
            }
            importer.clipAnimations = clips;
            importer.SaveAndReimport();
            var result = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().FirstOrDefault(item => !item.name.StartsWith("__preview__", StringComparison.Ordinal));
            if (result == null) throw new InvalidOperationException("No imported animation in " + path);
            Debug.Log("ABBY_MESHTINT_CLIP: " + path + " -> " + result.name);
            return result;
        }

        private static AnimatorController CreateController(string name, AnimationClip idle, AnimationClip movement)
        {
            var path = GeneratedPath + "/" + name + ".controller";
            var existing = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
            if (existing != null)
            {
                // Keep the controller GUID on repeated preparations.
                foreach (var state in existing.layers[0].stateMachine.states)
                    state.state.motion = state.state.name == "Rest" ? idle : movement;
                EditorUtility.SetDirty(existing);
                return existing;
            }
            var controller = AnimatorController.CreateAnimatorControllerAtPath(path);
            controller.AddParameter("Speed", AnimatorControllerParameterType.Float);
            var machine = controller.layers[0].stateMachine;
            var rest = machine.AddState("Rest");
            var move = machine.AddState("Move");
            rest.motion = idle;
            move.motion = movement;
            machine.defaultState = rest;
            var begin = rest.AddTransition(move);
            begin.hasExitTime = false;
            begin.duration = .12f;
            begin.AddCondition(AnimatorConditionMode.Greater, .05f, "Speed");
            var stop = move.AddTransition(rest);
            stop.hasExitTime = false;
            stop.duration = .12f;
            stop.AddCondition(AnimatorConditionMode.Less, .05f, "Speed");
            // No combat clip is mapped as affection. VisualPresenter supplies a friendly hop.
            return controller;
        }

        private static VisualDefinition CreateVisual(string name, GameObject source, RuntimeAnimatorController controller, float height, float lift, bool removeWeapons)
        {
            var instance = UnityEngine.Object.Instantiate(source);
            instance.name = name;
            instance.transform.position = Vector3.zero;
            instance.transform.rotation = Quaternion.identity;
            instance.transform.localScale = Vector3.one;
            if (removeWeapons)
                foreach (var child in instance.GetComponentsInChildren<Transform>(true).ToArray())
                    if (child != null && child != instance.transform && (child.name.StartsWith("Bow", StringComparison.OrdinalIgnoreCase)
                        || child.name.StartsWith("Quiver", StringComparison.OrdinalIgnoreCase) || child.name.StartsWith("Arrow", StringComparison.OrdinalIgnoreCase)))
                        UnityEngine.Object.DestroyImmediate(child.gameObject);
            foreach (var collider in instance.GetComponentsInChildren<Collider>(true)) UnityEngine.Object.DestroyImmediate(collider);
            foreach (var rigidbody in instance.GetComponentsInChildren<Rigidbody>(true)) UnityEngine.Object.DestroyImmediate(rigidbody);
            var animator = instance.GetComponentInChildren<Animator>();
            if (animator == null) animator = instance.AddComponent<Animator>();
            animator.runtimeAnimatorController = controller;
            animator.applyRootMotion = false;
            animator.cullingMode = AnimatorCullingMode.AlwaysAnimate;
            animator.Rebind();
            controller.animationClips.First(clip => !clip.name.StartsWith("__preview__", StringComparison.Ordinal)).SampleAnimation(animator.gameObject, 0f);
            var renderers = instance.GetComponentsInChildren<Renderer>().Where(renderer => renderer.enabled && renderer.gameObject.activeInHierarchy).ToArray();
            if (renderers.Length == 0) throw new InvalidOperationException("No visible geometry in " + source.name);
            var bounds = renderers[0].bounds;
            foreach (var renderer in renderers.Skip(1)) bounds.Encapsulate(renderer.bounds);
            var scale = height / Mathf.Max(.01f, bounds.size.y);
            var model = PrefabUtility.SaveAsPrefabAsset(instance, GeneratedPath + "/" + name + ".prefab");
            UnityEngine.Object.DestroyImmediate(instance);
            var path = GeneratedPath + "/" + name + ".asset";
            var definition = AssetDatabase.LoadAssetAtPath<VisualDefinition>(path);
            if (definition == null)
            {
                definition = ScriptableObject.CreateInstance<VisualDefinition>();
                AssetDatabase.CreateAsset(definition, path);
            }
            definition.AppearanceId = "cute-" + name;
            definition.ModelPrefab = model;
            definition.AnimatorController = controller;
            definition.LocalScale = Vector3.one * scale;
            definition.LocalPosition = new Vector3(0f, -bounds.min.y * scale + lift, 0f);
            definition.CelebrateTrigger = "";
            EditorUtility.SetDirty(definition);
            Debug.Log($"ABBY_MESHTINT_VISUAL: {name}; bounds={bounds.size}, scale={scale}, offset={definition.LocalPosition}");
            return definition;
        }

        private static void DecorateForest()
        {
            var scenery = GameObject.Find("Replaceable meadow scenery").transform;
            foreach (var child in scenery.Cast<Transform>().ToArray())
                if (child.name.StartsWith("Round tree", StringComparison.Ordinal) || child.name.StartsWith("Little meadow stone", StringComparison.Ordinal))
                    UnityEngine.Object.DestroyImmediate(child.gameObject);
            var positions = new[] { new Vector3(-6.8f, 0f, 3.8f), new Vector3(-5f, 0f, 5.5f), new Vector3(5.8f, 0f, 4.5f), new Vector3(7.2f, 0f, 1.7f), new Vector3(-7f, 0f, -3.5f) };
            for (var i = 0; i < positions.Length; i++)
                Place("Nature/" + (i % 2 == 0 ? "Tree 02 Green Twoside" : "Tree 03 Green Twoside") + ".prefab", positions[i], 3.1f, i * 47f, scenery);
            for (var i = 0; i < 10; i++)
            {
                var angle = i * 2.399963f;
                var position = new Vector3(Mathf.Cos(angle) * 6.3f, 0f, Mathf.Sin(angle) * 4.4f);
                Place("Rocks/Rock 01.prefab", position, .35f + i % 3 * .1f, i * 63f, scenery);
                if (i % 3 == 0) Place("Nature/Mushroom 01.prefab", position + new Vector3(.55f, 0f, .2f), .35f, i * 32f, scenery);
            }
            Place("Structures and Buildings/Arch Gate 01.prefab", new Vector3(3.6f, 0f, 4.5f), 2.4f, 0f, scenery);
        }

        private static void Place(string path, Vector3 position, float height, float yaw, Transform parent)
        {
            var source = AssetDatabase.LoadAssetAtPath<GameObject>(ForestPath + path);
            if (source == null) throw new InvalidOperationException("Missing forest art: " + path);
            var instance = UnityEngine.Object.Instantiate(source, parent);
            instance.transform.position = Vector3.zero;
            instance.transform.rotation = Quaternion.Euler(0f, yaw, 0f);
            instance.transform.localScale = Vector3.one;
            foreach (var collider in instance.GetComponentsInChildren<Collider>()) UnityEngine.Object.DestroyImmediate(collider);
            var renderers = instance.GetComponentsInChildren<Renderer>();
            var bounds = renderers[0].bounds;
            foreach (var renderer in renderers.Skip(1)) bounds.Encapsulate(renderer.bounds);
            var scale = height / Mathf.Max(.01f, bounds.size.y);
            instance.transform.localScale = Vector3.one * scale;
            instance.transform.position = position + Vector3.down * bounds.min.y * scale;
        }

        [MenuItem("Abby Camp/Licensed Cute Series/Validate meadow")]
        public static void Validate()
        {
            CampSceneBuilder.ValidateScene(ScenePath, PresentationPath, scene =>
            {
                foreach (var name in new[] { "chick", "fledgling", "bird" })
                {
                    var definition = AssetDatabase.LoadAssetAtPath<VisualDefinition>(GeneratedPath + "/" + name + ".asset");
                    if (definition == null || definition.ModelPrefab == null || definition.AnimatorController == null || definition.Portrait == null)
                        throw new InvalidOperationException("Incomplete licensed companion: " + name);
                    if (definition.AnimatorController.animationClips.Length < 2)
                        throw new InvalidOperationException("Missing idle/movement mapping: " + name);
                }
                var companion = scene.GetRootGameObjects()
                    .SelectMany(root => root.GetComponentsInChildren<CompanionFollower>())
                    .FirstOrDefault(candidate => candidate.gameObject.activeInHierarchy);
                if (companion.GetComponent<CampEntityIdentity>().ContentId != "starter-companion")
                    throw new InvalidOperationException("Purchased art changed companion identity.");
                foreach (var renderer in scene.GetRootGameObjects()
                    .SelectMany(root => root.GetComponentsInChildren<Renderer>())
                    .Where(candidate => candidate.gameObject.activeInHierarchy))
                    foreach (var material in renderer.sharedMaterials)
                    {
                        if (material == null || material.shader == null || !material.shader.isSupported)
                            throw new InvalidOperationException("Missing/unsupported scene material on " + renderer.name);
                        if (AssetDatabase.GetAssetPath(material).StartsWith(SourcePath, StringComparison.Ordinal)
                            && (!material.HasProperty("_BaseMap") || material.GetTexture("_BaseMap") == null))
                            throw new InvalidOperationException("Purchased scene material has no supplied texture: " + material.name);
                    }
                Debug.Log("ABBY_MESHTINT_VALIDATED: three animated stage definitions, portraits, unchanged companion identity, scene materials.");
            });
        }
    }
}
