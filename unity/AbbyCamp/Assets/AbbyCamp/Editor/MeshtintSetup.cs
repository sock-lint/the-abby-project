using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using AbbyCamp.Presentation;
using AbbyCamp.World;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
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
        private static readonly Dictionary<Material, Material> ForestMaterials = new Dictionary<Material, Material>();

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
            SoftenWelcomeMat(settings);
            EditorSceneManager.SaveScene(UnityEngine.SceneManagement.SceneManager.GetActiveScene(), ScenePath);
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
            ForestMaterials.Clear();
            UnityEngine.Object.FindFirstObjectByType<CampPhoneCamera>().ConfigureFraming(6.7f, new Vector3(-.35f, 1.1f, .5f));
            var sun = UnityEngine.Object.FindObjectsByType<Light>(FindObjectsSortMode.None).First(light => light.type == LightType.Directional);
            sun.intensity = .95f;
            sun.color = new Color(1f, .98f, .96f);
            RenderSettings.ambientLight = new Color(.67f, .69f, .7f);
            var scenery = GameObject.Find("Replaceable meadow scenery").transform;
            foreach (var child in scenery.Cast<Transform>().ToArray())
                if (child.name.StartsWith("Round tree", StringComparison.Ordinal) || child.name.StartsWith("Little meadow stone", StringComparison.Ordinal)
                    || child.name.StartsWith("Meadow flower", StringComparison.Ordinal) || child.name.StartsWith("Tree collision", StringComparison.Ordinal))
                    UnityEngine.Object.DestroyImmediate(child.gameObject);
            var forest = new GameObject("Purchased woodland backdrop").transform;
            forest.SetParent(scenery, false);

            // The purchased ground is appearance only. The existing flat box and
            // perimeter still own movement; no imported terrain physics is added.
            GameObject.Find("Soft meadow island").SetActive(false);
            GameObject.Find("Meadow edge").SetActive(false);
            PlaceFootprint("Grounds and Platforms/Ground 01 Soft Edge.prefab", Vector3.zero, 25f, 22f, -.015f, 0f, forest);
            GameObject.Find("Welcome clearing").SetActive(false);
            PlaceFootprint("Grounds and Platforms/Soil 01.prefab", new Vector3(-.7f, 0f, .7f), 8.2f, 7.6f, .012f, -12f, forest);
            for (var i = 0; i < 5; i++)
            {
                GameObject.Find("Stepping stone " + (i + 1)).SetActive(false);
                var position = Vector3.Lerp(new Vector3(1f, 0f, -4.7f), new Vector3(-3f, 0f, 2.5f), i / 4f);
                PlaceFootprint("Steps/Stone Step 01.prefab", position, 1.1f, .8f, .035f, 18f + i * 11f, forest);
            }

            // Tall silhouettes stay beyond the walkable north/west rim. The
            // southeast foreground stays low for the following phone camera.
            var trees = new[] {
                new Vector3(-10f, 0f, -5f), new Vector3(-10.3f, 0f, -1.8f), new Vector3(-10f, 0f, 1.5f),
                new Vector3(-9.2f, 0f, 4.8f), new Vector3(-7.3f, 0f, 7.4f), new Vector3(-4.2f, 0f, 8.3f),
                new Vector3(-1.1f, 0f, 8.9f), new Vector3(2.2f, 0f, 8.7f), new Vector3(5.5f, 0f, 8.2f),
                new Vector3(8.3f, 0f, 6.8f), new Vector3(10.2f, 0f, 4.2f), new Vector3(11f, 0f, 1.1f),
                new Vector3(-11.5f, 0f, 6f), new Vector3(-6f, 0f, 10.5f), new Vector3(.7f, 0f, 11f),
                new Vector3(7f, 0f, 10f),
                new Vector3(-6.5f, 0f, 3.1f), new Vector3(-6.6f, 0f, 5.6f),
                new Vector3(-2.4f, 0f, 5.9f), new Vector3(.5f, 0f, 5.9f)
            };
            for (var i = 0; i < trees.Length; i++)
            {
                var tree = i % 4 == 0 ? "Tree 05" : i % 3 == 0 ? "Tree 03 Orange Twoside"
                    : i % 2 == 0 ? "Tree 03 Green Twoside" : "Tree 02 Green Twoside";
                Place("Nature/" + tree + ".prefab", trees[i], i < 16 ? 3.6f + i % 3 * .45f : 2.65f, i * 47f, forest, false);
            }

            // A broken garden gateway frames the bloom side, with small ruin
            // fragments along the woodland rather than across the task route.
            Place("Structures and Buildings/Arch Gate 01.prefab", new Vector3(3.8f, 0f, 6.2f), 3.3f, -18f, forest);
            Place("Structures and Buildings/Arch Gate 01.prefab", new Vector3(-5.2f, 0f, 5.9f), 2.7f, -18f, forest);
            Place("Structures and Buildings/Arch Gate Debris 01.prefab", new Vector3(6.9f, 0f, 5.4f), .7f, 35f, forest);
            Place("Structures and Buildings/Ancient Pillar 01.prefab", new Vector3(7.8f, 0f, 3.6f), 1.9f, 24f, forest);
            Place("Structures and Buildings/Ancient Pillar 01.prefab", new Vector3(-7.8f, 0f, 5.3f), 1.45f, 66f, forest);
            Place("Structures and Buildings/Arch Gate Debris 02.prefab", new Vector3(-8.1f, 0f, .1f), .55f, 80f, forest);

            var pockets = new[] {
                new Vector3(-7f, 0f, -3.7f), new Vector3(-7.4f, 0f, -.8f), new Vector3(-6.7f, 0f, 1.6f),
                new Vector3(-5.8f, 0f, 5.8f), new Vector3(-2.5f, 0f, 6.3f), new Vector3(.6f, 0f, 6.4f),
                new Vector3(6.1f, 0f, 3.5f), new Vector3(7f, 0f, .5f), new Vector3(6.6f, 0f, -2.6f),
                new Vector3(4.3f, 0f, -4.9f), new Vector3(-2.8f, 0f, -4.9f)
            };
            for (var i = 0; i < pockets.Length; i++)
            {
                Place("Rocks/Rock 01.prefab", pockets[i], .3f + i % 3 * .12f, i * 63f, forest);
                Place("Nature/Grass 01A Two Sided.prefab", pockets[i] + new Vector3(.5f, 0f, .3f), .45f, i * 39f, forest, false);
                if (i % 2 == 0)
                    Place("Nature/Mushroom " + (i % 4 == 0 ? "01" : "02") + ".prefab", pockets[i] + new Vector3(-.35f, 0f, .45f), .35f, i * 32f, forest);
            }
            AssetDatabase.SaveAssets();
            ValidateForest();
        }

        private static void SoftenWelcomeMat(CampPresentationDefinition palette)
        {
            var welcome = GameObject.Find("Task board welcome mat");
            if (welcome == null) throw new InvalidOperationException("The task board welcome mat is missing.");
            welcome.transform.localScale = Vector3.Scale(welcome.transform.localScale, new Vector3(.65f, 1f, .65f));
            var welcomeMaterial = ForestMaterial(welcome.GetComponent<Renderer>().sharedMaterial);
            welcomeMaterial.SetColor("_BaseColor", Color.Lerp(palette.Grass, palette.Paper, .45f));
            welcome.GetComponent<Renderer>().sharedMaterial = welcomeMaterial;
            EditorUtility.SetDirty(welcomeMaterial);
            AssetDatabase.SaveAssets();
        }

        private static Material ForestMaterial(Material source)
        {
            if (ForestMaterials.TryGetValue(source, out var known)) return known;
            var path = GeneratedPath + "/forest-" + AssetDatabase.AssetPathToGUID(AssetDatabase.GetAssetPath(source)) + ".mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                material = new Material(source);
                AssetDatabase.CreateAsset(material, path);
            }
            else material.CopyPropertiesFromMaterial(source);
            var palette = AssetDatabase.LoadAssetAtPath<CampPresentationDefinition>(PresentationPath);
            var name = source.name;
            if (name == "Forest Ruins")
            {
                material.SetTexture("_BaseMap", SoftForestAtlas(source.GetTexture("_BaseMap") as Texture2D, palette));
                material.SetColor("_BaseColor", Color.white);
            }
            else if (name.Contains("Leaves"))
                material.SetColor("_BaseColor", name.Contains("Orange") ? Color.Lerp(palette.Primary, palette.Paper, .64f)
                    : name.Contains("Blue") ? palette.Sky : Color.Lerp(palette.Grass, palette.Paper, .12f));
            else if (name.Contains("Grass")) material.SetColor("_BaseColor", palette.Grass);
            EditorUtility.SetDirty(material);
            ForestMaterials.Add(source, material);
            return material;
        }

        private static Texture2D SoftForestAtlas(Texture2D source, CampPresentationDefinition palette)
        {
            if (source == null) throw new InvalidOperationException("The supplied Forest Ruins atlas is missing.");
            // Read a private copy, never edit the purchased source pixels or its
            // importer. Keep the atlas detail/alpha while softening its colors.
            var sourcePath = AssetDatabase.GetAssetPath(source);
            var copyPath = GeneratedPath + "/forest-palette-source" + Path.GetExtension(sourcePath);
            File.Copy(sourcePath, copyPath, true);
            AssetDatabase.ImportAsset(copyPath, ImportAssetOptions.ForceSynchronousImport);
            var copyImporter = (TextureImporter)AssetImporter.GetAtPath(copyPath);
            copyImporter.isReadable = true;
            copyImporter.maxTextureSize = 512;
            copyImporter.textureCompression = TextureImporterCompression.Uncompressed;
            copyImporter.mipmapEnabled = false;
            copyImporter.SaveAndReimport();
            var copy = AssetDatabase.LoadAssetAtPath<Texture2D>(copyPath);
            var pixels = copy.GetPixels();
            for (var i = 0; i < pixels.Length; i++)
            {
                var original = pixels[i];
                Color.RGBToHSV(original, out var hue, out var saturation, out var value);
                var tint = saturation < .15f ? Color.Lerp(palette.Sky, palette.Paper, .55f)
                    : hue >= .15f && hue < .5f ? Color.Lerp(palette.Grass, palette.Paper, .12f)
                    : hue < .045f && saturation > .55f ? Color.Lerp(palette.Accent, palette.Paper, .2f)
                    : hue < .15f ? Color.Lerp(palette.Path, Color.Lerp(palette.Accent, palette.Paper, .65f), .5f)
                    : Color.Lerp(palette.Sky, palette.Paper, .2f);
                tint *= Mathf.Lerp(.45f, .88f, Mathf.Sqrt(value));
                tint.a = original.a;
                pixels[i] = tint;
            }
            var softened = new Texture2D(copy.width, copy.height, TextureFormat.RGBA32, false);
            softened.SetPixels(pixels);
            softened.Apply();
            var path = GeneratedPath + "/forest-soft-atlas.png";
            File.WriteAllBytes(path, softened.EncodeToPNG());
            UnityEngine.Object.DestroyImmediate(softened);
            AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceSynchronousImport);
            var importer = (TextureImporter)AssetImporter.GetAtPath(path);
            importer.maxTextureSize = 512;
            importer.alphaIsTransparency = true;
            importer.isReadable = false;
            importer.SaveAndReimport();
            return AssetDatabase.LoadAssetAtPath<Texture2D>(path);
        }

        private static GameObject ForestInstance(string path, float yaw, Transform parent)
        {
            var source = AssetDatabase.LoadAssetAtPath<GameObject>(ForestPath + path);
            if (source == null) throw new InvalidOperationException("Missing forest art: " + path);
            var instance = UnityEngine.Object.Instantiate(source, parent);
            instance.name = source.name;
            instance.transform.position = Vector3.zero;
            instance.transform.rotation = Quaternion.Euler(0f, yaw, 0f);
            instance.transform.localScale = Vector3.one;
            foreach (var collider in instance.GetComponentsInChildren<Collider>(true)) UnityEngine.Object.DestroyImmediate(collider);
            foreach (var rigidbody in instance.GetComponentsInChildren<Rigidbody>(true)) UnityEngine.Object.DestroyImmediate(rigidbody);
            foreach (var child in instance.GetComponentsInChildren<Transform>(true))
                GameObjectUtility.SetStaticEditorFlags(child.gameObject, StaticEditorFlags.BatchingStatic);
            foreach (var renderer in instance.GetComponentsInChildren<Renderer>(true))
                renderer.sharedMaterials = renderer.sharedMaterials.Select(ForestMaterial).ToArray();
            return instance;
        }

        private static Bounds ForestBounds(GameObject instance)
        {
            var renderers = instance.GetComponentsInChildren<Renderer>().Where(renderer => renderer.enabled).ToArray();
            if (renderers.Length == 0) throw new InvalidOperationException("No visible forest geometry: " + instance.name);
            var bounds = renderers[0].bounds;
            foreach (var renderer in renderers.Skip(1)) bounds.Encapsulate(renderer.bounds);
            if (bounds.size.x <= .001f || bounds.size.z <= .001f)
                throw new InvalidOperationException("Degenerate forest geometry: " + instance.name);
            return bounds;
        }

        private static void Place(string path, Vector3 position, float height, float yaw, Transform parent, bool shadows = true)
        {
            var instance = ForestInstance(path, yaw, parent);
            var bounds = ForestBounds(instance);
            if (bounds.size.y <= .001f) throw new InvalidOperationException("A height-scaled forest prop must have height: " + instance.name);
            var scale = height / bounds.size.y;
            instance.transform.localScale = Vector3.one * scale;
            instance.transform.position = position - new Vector3(bounds.center.x, bounds.min.y, bounds.center.z) * scale;
            if (!shadows)
                foreach (var renderer in instance.GetComponentsInChildren<Renderer>())
                    renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        }

        private static void PlaceFootprint(string path, Vector3 position, float width, float depth, float top, float yaw, Transform parent)
        {
            var instance = ForestInstance(path, yaw, parent);
            var bounds = ForestBounds(instance);
            var scale = Mathf.Min(width / bounds.size.x, depth / bounds.size.z);
            instance.transform.localScale = Vector3.one * scale;
            instance.transform.position = position + new Vector3(-bounds.center.x * scale, top - bounds.max.y * scale, -bounds.center.z * scale);
            foreach (var renderer in instance.GetComponentsInChildren<Renderer>())
                renderer.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        }

        private static void ValidateForest()
        {
            var forest = GameObject.Find("Purchased woodland backdrop");
            if (forest == null) throw new InvalidOperationException("The purchased woodland backdrop is missing; prepare the licensed meadow again.");
            if (forest.GetComponentsInChildren<Collider>(true).Length > 0 || forest.GetComponentsInChildren<Rigidbody>(true).Length > 0)
                throw new InvalidOperationException("Purchased scenery must not replace the flat gameplay physics.");
            var renderers = forest.GetComponentsInChildren<Renderer>().Where(renderer => renderer.enabled).ToArray();
            long triangles = 0;
            foreach (var filter in forest.GetComponentsInChildren<MeshFilter>())
            {
                if (filter.sharedMesh == null) throw new InvalidOperationException("Missing forest mesh on " + filter.name);
                for (var i = 0; i < filter.sharedMesh.subMeshCount; i++) triangles += (long)filter.sharedMesh.GetIndexCount(i) / 3;
            }
            var shadowCasters = renderers.Count(renderer => renderer.shadowCastingMode != UnityEngine.Rendering.ShadowCastingMode.Off);
            if (renderers.Length > 100 || triangles > 150000 || shadowCasters > 25)
                throw new InvalidOperationException($"Forest exceeds the phone scene budget: {renderers.Length} renderers, {triangles} triangles, {shadowCasters} shadow casters.");
            Debug.Log($"ABBY_MESHTINT_FOREST: {forest.transform.childCount} purchased props, {renderers.Length} renderers, {triangles} triangles, {shadowCasters} shadow casters; flat gameplay physics preserved.");
        }

        [MenuItem("Abby Camp/Licensed Cute Series/Validate meadow")]
        public static void Validate()
        {
            CampSceneBuilder.ValidateScene(ScenePath, PresentationPath);
            ValidateForest();
            foreach (var name in new[] { "chick", "fledgling", "bird" })
            {
                var definition = AssetDatabase.LoadAssetAtPath<VisualDefinition>(GeneratedPath + "/" + name + ".asset");
                if (definition == null || definition.ModelPrefab == null || definition.AnimatorController == null || definition.Portrait == null)
                    throw new InvalidOperationException("Incomplete licensed companion: " + name);
                if (definition.AnimatorController.animationClips.Length < 2)
                    throw new InvalidOperationException("Missing idle/movement mapping: " + name);
            }
            var companion = UnityEngine.Object.FindAnyObjectByType<CompanionFollower>();
            if (companion.GetComponent<CampEntityIdentity>().ContentId != "starter-companion")
                throw new InvalidOperationException("Purchased art changed companion identity.");
            foreach (var renderer in UnityEngine.Object.FindObjectsByType<Renderer>())
                foreach (var material in renderer.sharedMaterials)
                {
                    if (material == null || material.shader == null || !material.shader.isSupported)
                        throw new InvalidOperationException("Missing/unsupported scene material on " + renderer.name);
                    if (AssetDatabase.GetAssetPath(material).StartsWith(SourcePath, StringComparison.Ordinal)
                        && (!material.HasProperty("_BaseMap") || material.GetTexture("_BaseMap") == null))
                        throw new InvalidOperationException("Purchased scene material has no supplied texture: " + material.name);
                }
            Debug.Log("ABBY_MESHTINT_VALIDATED: three animated stage definitions, portraits, unchanged companion identity, scene materials.");
        }
    }
}
