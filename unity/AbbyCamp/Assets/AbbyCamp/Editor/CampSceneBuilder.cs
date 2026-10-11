using System;
using System.IO;
using System.Linq;
using AbbyCamp.Presentation;
using AbbyCamp.UI;
using AbbyCamp.World;
using UnityEditor;
using UnityEditor.Animations;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace AbbyCamp.Editor
{
    /// <summary>Reproducible meadow. Rebuilding preserves authored presentation references.</summary>
    public static class CampSceneBuilder
    {
        public const string ScenePath = "Assets/AbbyCamp/Scenes/Camp.unity";
        private const string GeneratedPath = "Assets/AbbyCamp/Generated";
        public const string PresentationPath = "Assets/AbbyCamp/Presentation/Meadow.asset";
        private static CampPresentationDefinition presentation;
        private const string NaturePath = "Assets/ThirdParty/Kenney/NatureKit/Models/";
        private static Material grass, darkGrass, path, wood, darkWood, paper, turquoise, orange, stone, rewardSparkles;

        [MenuItem("Abby Camp/Create or rebuild camp")]
        public static void Build()
        {
            BuildScene(null, ScenePath);
        }

        // Regenerate the public scene independently before preparing an older
        // local licensed scene; ValidateAll can then validate both together.
        public static void RebuildAndValidate()
        {
            Build();
            Validate();
        }

        public static void BuildScene(CampPresentationDefinition authored, string scenePath, Action decorate = null)
        {
            Directory.CreateDirectory("Assets/AbbyCamp/Scenes");
            Directory.CreateDirectory(GeneratedPath);
            AssetDatabase.Refresh();
            if (authored == null)
            {
                ConfigureKenneyImports();
                ConfigureStorybookImports();
            }
            presentation = authored != null ? authored : LoadPresentation();
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            MakeMaterials();
            BuildCameraAndLighting();
            BuildGround();
            BuildScenery();
            decorate?.Invoke();
            var companion = BuildCompanion(presentation.CompanionAppearance, presentation.AlternateCompanionAppearance);
            var gardenInput = new GameObject("Companion garden input").AddComponent<CampGardenInput>();
            gardenInput.Configure(companion);
            Camera.main.GetComponent<CampPhoneCamera>().Configure(companion.transform);
            var session = new GameObject("CampSession").AddComponent<CampPrototypeController>();
            session.Configure(gardenInput, companion, presentation);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, scenePath);
            if (scenePath == ScenePath)
                EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            AssetDatabase.SaveAssets();
            Debug.Log("ABBY_CAMP_BUILD_OK: saved " + scenePath);
        }

        [MenuItem("Abby Camp/Validate prototype")]
        public static void Validate()
        {
            ValidateScene(ScenePath, PresentationPath);
        }

        public static void ValidateScene(string scenePath, string presentationPath, Action<Scene> additionalValidation = null)
        {
            // Validate saved source in isolation: appearance swaps must not modify
            // a contributor's open scene or serialize new instance IDs.
            var scene = EditorSceneManager.OpenPreviewScene(scenePath);
            try
            {
                var companion = FindSceneComponent<CompanionFollower>(scene);
                var gardenInput = FindSceneComponent<CampGardenInput>(scene);
                Require(companion != null && gardenInput != null, "Missing companion garden; regenerate this scene.");
                Require(FindSceneComponents<CompanionFollower>(scene, true).Length == 1,
                    "The garden must have one hero companion.");
                Require(FindSceneComponents<CampPlayerController>(scene, true).Length == 0
                    && FindSceneComponents<CampTaskBoard>(scene, true).Length == 0,
                    "Play must not require a walking avatar or task-board proximity; regenerate this scene.");
                Require(FindSceneComponent<CampPrototypeController>(scene) != null, "Missing session UI.");
                var authored = AssetDatabase.LoadAssetAtPath<CampPresentationDefinition>(presentationPath);
                Require(authored != null && companion.PrimaryAppearance == authored.CompanionAppearance
                    && companion.Appearance != null && companion.Appearance.Definition == authored.CompanionAppearance,
                    "Scene does not use its authored presentation references.");
                Require(authored.UiFont != null, "The shared Nunito UI font is missing.");
                ValidateSharedPalette(authored);
                var camera = FindSceneComponents<Camera>(scene)
                    .FirstOrDefault(candidate => candidate.enabled && candidate.CompareTag("MainCamera"));
                Require(camera != null && camera.orthographic
                    && camera.GetComponent<CampPhoneCamera>() != null
                    && camera.GetComponent<CampPhoneCamera>().Subject == companion.transform,
                    "The fixed garden camera must frame its companion.");
                Require(gardenInput.Companion == companion && gardenInput.InputEnabled, "The garden input must target its companion.");
                Require(FindSceneComponents<CharacterController>(scene, true).Length == 0
                    && !FindSceneComponents<Collider>(scene).Any(collider => collider.enabled),
                    "The fixed garden must not depend on movement or scenery physics.");
                Require(companion.transform.position == companion.AnchorPosition
                    && Quaternion.Angle(companion.transform.rotation, companion.AnchorRotation) < .001f,
                    "The companion must remain on its fixed garden anchor.");
                Require(companion.PrimaryAppearance != null && companion.SecondaryAppearance != null, "Companion needs two swappable appearances.");
                var originalDefinition = companion.Appearance.Definition;
                var beforePosition = companion.transform.position;
                var beforeRotation = companion.transform.rotation;
                var beforeScale = companion.transform.localScale;
                var identity = companion.GetComponent<CampEntityIdentity>();
                Require(identity != null, "Missing companion gameplay identity.");
                var originalId = identity.ContentId;
                companion.ApplyAppearance(companion.SecondaryAppearance);
                Require(companion.Appearance.Definition == companion.SecondaryAppearance, "Appearance switch did not apply.");
                Require(companion.transform.position == beforePosition && companion.transform.rotation == beforeRotation && companion.transform.localScale == beforeScale, "Appearance switch moved gameplay root.");
                Require(identity.ContentId == originalId && gardenInput.Companion == companion,
                    "Appearance switch changed companion identity or interaction.");
                companion.ApplyAppearance(originalDefinition);
                var appearances = new[] { companion.PrimaryAppearance, companion.SecondaryAppearance };
                foreach (var definition in appearances)
                {
                    Require(definition != null && (definition.ModelPrefab != null || definition.Portrait != null), "Missing model or portrait for an appearance.");
                    // A static sprite/model is valid: VisualPresenter supplies local feedback.
                    // An imported animation controller is optional, never a condition on identity.
                }
                additionalValidation?.Invoke(scene);
                Debug.Log("ABBY_CAMP_VALIDATE_OK: fixed companion garden, tap interaction, authored presentation, and appearance swap preserve identity and anchor.");
            }
            finally
            {
                EditorSceneManager.ClosePreviewScene(scene);
            }
        }

        private static T FindSceneComponent<T>(Scene scene) where T : Component
        {
            return FindSceneComponents<T>(scene).FirstOrDefault();
        }

        private static T[] FindSceneComponents<T>(Scene scene, bool includeInactive = false) where T : Component
        {
            return scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<T>(includeInactive))
                .Where(component => includeInactive || component.gameObject.activeInHierarchy)
                .ToArray();
        }

        private static CampPresentationDefinition LoadPresentation()
        {
            Directory.CreateDirectory("Assets/AbbyCamp/Presentation");
            var settings = AssetDatabase.LoadAssetAtPath<CampPresentationDefinition>(PresentationPath);
            if (settings == null)
            {
                settings = ScriptableObject.CreateInstance<CampPresentationDefinition>();
                AssetDatabase.CreateAsset(settings, PresentationPath);
            }
            // The fixed garden does not ship an unused avatar through its
            // presentation. Keep authored companion references across builds.
            settings.PlayerAppearance = null;
            if (settings.CompanionAppearance == null)
                settings.CompanionAppearance = CreateDragonDefinition(settings.Accent);
            if (settings.AlternateCompanionAppearance == null)
                settings.AlternateCompanionAppearance = CreateDefinition("companion-fox", "Assets/ThirdParty/Kenney/CubePets/Models/animal-fox.fbx", .8f, "dance", settings.Accent);
            if (settings.MemoryBloom == null)
                settings.MemoryBloom = AssetDatabase.LoadAssetAtPath<Sprite>("Assets/AbbyCamp/Art/Shared/memory-bloom.png");
            if (settings.UiFont == null)
                settings.UiFont = AssetDatabase.LoadAssetAtPath<Font>("Assets/AbbyCamp/Art/Shared/Nunito-SemiBold.ttf");
            EditorUtility.SetDirty(settings);
            return settings;
        }

        private static VisualDefinition CreateDragonDefinition(Color fallback)
        {
            const string location = "Assets/AbbyCamp/Presentation/meadow-dragon.asset";
            var existing = AssetDatabase.LoadAssetAtPath<VisualDefinition>(location);
            if (existing != null) return existing;
            var definition = ScriptableObject.CreateInstance<VisualDefinition>();
            definition.AppearanceId = "meadow-dragon";
            definition.PlaceholderColor = fallback;
            definition.Portrait = AssetDatabase.LoadAssetAtPath<Sprite>("Assets/AbbyCamp/Art/Shared/dragon-idle.png");
            definition.HappyPortrait = AssetDatabase.LoadAssetAtPath<Sprite>("Assets/AbbyCamp/Art/Shared/dragon-happy.png");
            definition.BlinkPortrait = AssetDatabase.LoadAssetAtPath<Sprite>("Assets/AbbyCamp/Art/Shared/dragon-blink.png");
            definition.PortraitHeight = 1.9f;
            AssetDatabase.CreateAsset(definition, location);
            return definition;
        }

        private static void ConfigureStorybookImports()
        {
            foreach (var filename in new[] { "dragon-idle.png", "dragon-happy.png", "dragon-blink.png", "memory-bloom.png" })
            {
                var importer = AssetImporter.GetAtPath("Assets/AbbyCamp/Art/Shared/" + filename) as TextureImporter;
                if (importer == null) continue;
                importer.textureType = TextureImporterType.Sprite;
                importer.spriteImportMode = SpriteImportMode.Single;
                importer.spritePixelsPerUnit = 100;
                importer.alphaIsTransparency = true;
                importer.mipmapEnabled = false;
                importer.wrapMode = TextureWrapMode.Clamp;
                importer.maxTextureSize = 1024;
                importer.SaveAndReimport();
            }
        }

        [Serializable] private sealed class SharedManifest { public int schema_version; public SharedPalette palette; }
        [Serializable] private sealed class SharedPalette
        {
            public string paper, ink, primary, grass, accent, sky, gold;
        }

        private static void ValidateSharedPalette(CampPresentationDefinition settings)
        {
            var source = Resources.Load<TextAsset>("StorybookPresentation");
            Require(source != null, "Shared storybook presentation manifest is missing.");
            var manifest = JsonUtility.FromJson<SharedManifest>(source.text);
            Require(manifest != null && manifest.schema_version == 1 && manifest.palette != null, "Unsupported shared presentation schema.");
            void Match(Color actual, string expected, string label)
            {
                Require(ColorUtility.TryParseHtmlString(expected, out var canonical), "Missing shared " + label + " color.");
                Require(Mathf.Abs(actual.r - canonical.r) < .00001f && Mathf.Abs(actual.g - canonical.g) < .00001f && Mathf.Abs(actual.b - canonical.b) < .00001f,
                    "World " + label + " differs from the shared web presentation manifest.");
            }
            Match(settings.Paper, manifest.palette.paper, "paper");
            Match(settings.Ink, manifest.palette.ink, "ink");
            Match(settings.Primary, manifest.palette.primary, "primary");
            Match(settings.Grass, manifest.palette.grass, "grass");
            Match(settings.Accent, manifest.palette.accent, "accent");
            Match(settings.Sky, manifest.palette.sky, "sky");
            Match(settings.Path, manifest.palette.gold, "gold");
        }

        private static void Require(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
        }

        private static void MakeMaterials()
        {
            grass = MakeMaterial("Grass", presentation.Grass);
            darkGrass = MakeMaterial("Raised meadow", presentation.GrassEdge);
            path = MakeMaterial("Sandstone path", presentation.Path);
            wood = MakeMaterial("Warm cedar", new Color(.68f, .52f, .39f));
            darkWood = MakeMaterial("Deep cedar", new Color(.48f, .38f, .32f));
            paper = MakeMaterial("Task paper", presentation.Paper);
            turquoise = MakeMaterial("Camp teal", presentation.Primary);
            orange = MakeMaterial("Camp gold", presentation.Accent);
            stone = MakeMaterial("Slate stones", new Color(.72f, .77f, .75f));
            rewardSparkles = MakeMaterial("Reward sparkles", presentation.Path);
            var particleShader = Shader.Find("Universal Render Pipeline/Particles/Unlit");
            if (particleShader != null) rewardSparkles.shader = particleShader;
            EditorUtility.SetDirty(rewardSparkles);
        }

        private static void ConfigureKenneyImports()
        {
            var modelPaths = AssetDatabase.FindAssets("t:Model", new[] { "Assets/ThirdParty/Kenney" }).Select(AssetDatabase.GUIDToAssetPath).ToArray();
            foreach (var modelPath in modelPaths)
            {
                var importer = AssetImporter.GetAtPath(modelPath) as ModelImporter;
                if (importer == null) continue;
                var isAnimated = modelPath.Contains("BlockyCharacters") || modelPath.Contains("CubePets");
                if (isAnimated)
                {
                    importer.animationType = ModelImporterAnimationType.Generic;
                    importer.importAnimation = true;
                    importer.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                    var clips = importer.defaultClipAnimations;
                    foreach (var clip in clips)
                    {
                        var clipName = clip.name.ToLowerInvariant().Split('|').Last();
                        clip.loopTime = clipName == "idle" || clipName == "walk" || clipName == "run" || clipName == "sprint";
                    }
                    importer.clipAnimations = clips;
                    importer.SaveAndReimport();
                }
                // The packs use standard FBX materials; remap each named material individually to URP.
                // Nature keeps its distinct submesh colors, while characters/pets retain supplied textures.
                var sourceMaterials = AssetDatabase.LoadAllAssetsAtPath(modelPath).OfType<Material>().ToArray();
                foreach (var source in sourceMaterials)
                {
                    var pack = modelPath.Contains("NatureKit") ? "nature" : modelPath.Contains("CubePets") ? "pets" : "character";
                    var safeName = string.Concat(source.name.Select(character => char.IsLetterOrDigit(character) || character == '-' || character == '_' ? character : '_'));
                    var materialPath = GeneratedPath + "/kenney-" + pack + "-" + safeName + ".mat";
                    var material = AssetDatabase.LoadAssetAtPath<Material>(materialPath);
                    if (material == null)
                    {
                        material = new Material(Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard"));
                        AssetDatabase.CreateAsset(material, materialPath);
                    }
                    material.color = source.HasProperty("_Color") ? source.color : Color.white;
                    var sourceTexture = source.mainTexture;
                    if (sourceTexture == null && pack == "pets")
                        sourceTexture = AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/ThirdParty/Kenney/CubePets/Models/Textures/colormap.png");
                    if (sourceTexture == null && pack == "character")
                    {
                        var textureName = Path.GetFileNameWithoutExtension(modelPath).Replace("character-", "texture-");
                        sourceTexture = AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/ThirdParty/Kenney/BlockyCharacters/Models/Textures/" + textureName + ".png");
                    }
                    material.mainTexture = sourceTexture;
                    if (material.HasProperty("_Smoothness")) material.SetFloat("_Smoothness", .12f);
                    EditorUtility.SetDirty(material);
                    importer.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), source.name), material);
                }
                importer.SaveAndReimport();
            }
            // Already remapped FBX materials may no longer appear as imported subassets on a
            // later rebuild. Update their referenced generated assets explicitly as well.
            foreach (var guid in AssetDatabase.FindAssets("t:Material", new[] { GeneratedPath }))
            {
                var materialPath = AssetDatabase.GUIDToAssetPath(guid);
                var filename = Path.GetFileNameWithoutExtension(materialPath);
                const string prefix = "kenney-nature-";
                if (!filename.StartsWith(prefix, StringComparison.Ordinal)) continue;
                var material = AssetDatabase.LoadAssetAtPath<Material>(materialPath);
                material.color = NatureColor(filename.Substring(prefix.Length), material.color);
                if (material.HasProperty("_Smoothness")) material.SetFloat("_Smoothness", .08f);
                EditorUtility.SetDirty(material);
            }
        }

        private static Color NatureColor(string name, Color fallback)
        {
            // Unity handles the material color-space conversion for these display palette values.
            switch (name.ToLowerInvariant())
            {
                case "leafsgreen": return new Color(.36f, .49f, .34f);
                case "leafsdark": return new Color(.27f, .39f, .29f);
                case "grass": return new Color(.43f, .54f, .36f);
                case "dirt": return new Color(.52f, .40f, .28f);
                case "rock":
                case "_defaultmat": return new Color(.48f, .53f, .50f);
                case "wood": return new Color(.51f, .36f, .23f);
                case "wooddark": return new Color(.36f, .26f, .18f);
                case "woodbark": return new Color(.42f, .29f, .20f);
                case "woodbarkdark": return new Color(.32f, .23f, .17f);
                case "woodinner": return new Color(.66f, .51f, .33f);
                case "coloryellow": return new Color(.82f, .68f, .32f);
                case "colorred": return new Color(.69f, .39f, .29f);
                case "colorreddark": return new Color(.52f, .29f, .23f);
                default: return fallback;
            }
        }

        private static Material MakeMaterial(string name, Color color)
        {
            var location = GeneratedPath + "/" + name + ".mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(location);
            if (material == null)
            {
                material = new Material(Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard"));
                AssetDatabase.CreateAsset(material, location);
            }
            material.color = color;
            if (material.HasProperty("_Smoothness")) material.SetFloat("_Smoothness", .12f);
            EditorUtility.SetDirty(material);
            return material;
        }

        private static void BuildCameraAndLighting()
        {
            var cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            cameraObject.transform.rotation = Quaternion.Euler(18f, 0f, 0f);
            var camera = cameraObject.AddComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = 4f;
            camera.nearClipPlane = .1f;
            camera.farClipPlane = 100f;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = presentation.Sky;
            cameraObject.AddComponent<CampPhoneCamera>();
            cameraObject.AddComponent<AudioListener>();
            var sun = new GameObject("Late afternoon sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.transform.rotation = Quaternion.Euler(48f, -38f, 0f);
            sun.color = new Color(1f, .96f, .88f);
            sun.intensity = 1.15f;
            sun.shadows = LightShadows.Soft;
            sun.shadowStrength = .55f;
            RenderSettings.ambientMode = AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(.76f, .78f, .75f);
            RenderSettings.ambientIntensity = 1f;
            RenderSettings.fog = false;
        }

        private static void BuildGround()
        {
            var environment = new GameObject("Meadow environment").transform;
            Shape("Soft meadow island", PrimitiveType.Cylinder, new Vector3(0f, -.3f, 0f), new Vector3(21f, .3f, 17f), grass, environment, false);
            Shape("Meadow edge", PrimitiveType.Cylinder, new Vector3(0f, -.62f, 0f), new Vector3(20.9f, .12f, 16.9f), darkGrass, environment, false);
            Disc("Welcome clearing", new Vector3(-.7f, .011f, .7f), 3.8f, path, environment);
            for (var i = 0; i < 5; i++)
            {
                var t = i / 4f;
                Disc("Stepping stone " + (i + 1), Vector3.Lerp(new Vector3(1f, .022f, -5f), new Vector3(-3f, .022f, 2.5f), t), .58f, paper, environment);
            }
        }

        private static void BuildScenery()
        {
            var scenery = new GameObject("Replaceable meadow scenery").transform;
            var treePositions = new[] { new Vector3(-3.2f, 0f, 3.8f), new Vector3(-1.4f, 0f, 5.5f), new Vector3(1.4f, 0f, 5.2f), new Vector3(3.2f, 0f, 2.4f), new Vector3(-3.5f, 0f, -.8f) };
            for (var i = 0; i < treePositions.Length; i++)
            {
                var p = treePositions[i];
                Shape("Round tree trunk " + i, PrimitiveType.Cylinder, p + Vector3.up * .95f, new Vector3(.25f, .95f, .25f), wood, scenery, false);
                Shape("Round tree crown " + i, PrimitiveType.Sphere, p + Vector3.up * 2.15f, new Vector3(2.3f, 2.3f, 2.3f), i % 2 == 0 ? darkGrass : turquoise, scenery, false);
                Shape("Round tree tuft " + i, PrimitiveType.Sphere, p + new Vector3(.65f, 2.3f, .3f), new Vector3(1.45f, 1.65f, 1.45f), grass, scenery, false);
            }
            for (var i = 0; i < 16; i++)
            {
                var angle = i * 2.399963f;
                var p = new Vector3(Mathf.Cos(angle) * (5f + i % 2), .12f, Mathf.Sin(angle) * 4.8f);
                Shape("Little meadow stone " + i, PrimitiveType.Sphere, p, new Vector3(.5f, .22f, .4f), stone, scenery, false);
                Flower("Meadow flower " + i, p + new Vector3(.5f, -.12f, .35f), i % 2 == 0 ? orange : paper, scenery);
            }
            Flower("Memory bloom decoration", new Vector3(2.6f, 0f, 3.4f), orange, scenery, 1.8f);
        }

        private static void Flower(string name, Vector3 ground, Material petals, Transform parent, float size = 1f)
        {
            Shape(name + " stem", PrimitiveType.Cylinder, ground + Vector3.up * .2f * size, new Vector3(.04f, .2f, .04f) * size, darkGrass, parent, false);
            var centre = ground + Vector3.up * .4f * size;
            for (var petal = 0; petal < 5; petal++)
            {
                var angle = petal * Mathf.PI * 2f / 5f;
                Shape(name + " petal", PrimitiveType.Sphere, centre + new Vector3(Mathf.Cos(angle) * .12f, 0, Mathf.Sin(angle) * .12f) * size, new Vector3(.16f, .06f, .16f) * size, petals, parent, false);
            }
            Shape(name + " centre", PrimitiveType.Sphere, centre + Vector3.up * .02f * size, new Vector3(.11f, .075f, .11f) * size, path, parent, false);
        }
        private static CompanionFollower BuildCompanion(VisualDefinition first, VisualDefinition second)
        {
            var companionObject = new GameObject("Companion");
            companionObject.transform.position = Vector3.zero;
            companionObject.transform.rotation = Quaternion.Euler(0f, 180f, 0f);
            companionObject.AddComponent<CampEntityIdentity>().Configure("starter-companion");
            companionObject.AddComponent<VisualPresenter>().SetVisual(first);
            companionObject.AddComponent<RewardReaction>().Configure(rewardSparkles);
            var companion = companionObject.AddComponent<CompanionFollower>();
            companion.Configure(first, second);
            return companion;
        }

        private static VisualDefinition CreateDefinition(string id, string modelPath, float targetHeight, string celebrationClip, Color fallback)
        {
            var definitionPath = GeneratedPath + "/" + id + ".asset";
            var definition = AssetDatabase.LoadAssetAtPath<VisualDefinition>(definitionPath);
            if (definition != null) return definition;
            definition = ScriptableObject.CreateInstance<VisualDefinition>();
            AssetDatabase.CreateAsset(definition, definitionPath);
            definition.AppearanceId = id;
            definition.ModelPrefab = AssetDatabase.LoadAssetAtPath<GameObject>(modelPath);
            definition.PlaceholderColor = fallback;
            definition.LocalEulerAngles = Vector3.zero;
            definition.LocalPosition = Vector3.zero;
            definition.LocalScale = Vector3.one;
            if (definition.ModelPrefab != null)
            {
                var temporary = UnityEngine.Object.Instantiate(definition.ModelPrefab);
                var bounds = GetBounds(temporary);
                var scale = targetHeight / Mathf.Max(.001f, bounds.size.y);
                definition.LocalScale = temporary.transform.localScale * scale;
                definition.LocalEulerAngles = temporary.transform.localEulerAngles;
                definition.LocalPosition = Vector3.up * (-bounds.min.y * scale);
                UnityEngine.Object.DestroyImmediate(temporary);
                definition.AnimatorController = CreateAnimator(id, modelPath, celebrationClip);
            }
            else Debug.LogWarning("Model unavailable; placeholder used: " + modelPath);
            EditorUtility.SetDirty(definition);
            return definition;
        }

        private static RuntimeAnimatorController CreateAnimator(string id, string modelPath, string celebrationClipName)
        {
            var clips = AssetDatabase.LoadAllAssetsAtPath(modelPath).OfType<AnimationClip>().Where(clip => !clip.name.StartsWith("__preview__", StringComparison.Ordinal)).ToArray();
            AnimationClip Find(string name) => clips.FirstOrDefault(clip => string.Equals(clip.name, name, StringComparison.OrdinalIgnoreCase) || clip.name.EndsWith("|" + name, StringComparison.OrdinalIgnoreCase));
            var idle = Find("idle");
            var walk = Find("walk");
            var celebrate = Find(celebrationClipName);
            if (idle == null || walk == null || celebrate == null)
            {
                Debug.LogWarning("Missing model animation mapping: " + id + " clips=" + string.Join(",", clips.Select(clip => clip.name)));
                return null;
            }
            var controllerPath = GeneratedPath + "/" + id + ".controller";
            AssetDatabase.DeleteAsset(controllerPath);
            var controller = AnimatorController.CreateAnimatorControllerAtPath(controllerPath);
            controller.AddParameter("Speed", AnimatorControllerParameterType.Float);
            controller.AddParameter("Celebrate", AnimatorControllerParameterType.Trigger);
            var machine = controller.layers[0].stateMachine;
            var idleState = machine.AddState("Idle");
            idleState.motion = idle;
            var walkState = machine.AddState("Walk");
            walkState.motion = walk;
            var celebrateState = machine.AddState("Celebrate");
            celebrateState.motion = celebrate;
            machine.defaultState = idleState;
            var walkTransition = idleState.AddTransition(walkState);
            walkTransition.hasExitTime = false;
            walkTransition.duration = .12f;
            walkTransition.AddCondition(AnimatorConditionMode.Greater, .08f, "Speed");
            var idleTransition = walkState.AddTransition(idleState);
            idleTransition.hasExitTime = false;
            idleTransition.duration = .12f;
            idleTransition.AddCondition(AnimatorConditionMode.Less, .08f, "Speed");
            var reaction = machine.AddAnyStateTransition(celebrateState);
            reaction.hasExitTime = false;
            reaction.duration = .1f;
            reaction.canTransitionToSelf = false;
            reaction.AddCondition(AnimatorConditionMode.If, 0f, "Celebrate");
            var reactionEnd = celebrateState.AddTransition(idleState);
            reactionEnd.hasExitTime = true;
            reactionEnd.exitTime = 1f;
            reactionEnd.duration = .12f;
            return controller;
        }

        private static GameObject PlaceImported(string filename, string name, Vector3 position, float height, float yaw, Transform parent)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(NaturePath + filename);
            if (prefab == null) return null;
            var instance = UnityEngine.Object.Instantiate(prefab);
            instance.name = name;
            instance.transform.SetParent(parent, true);
            instance.transform.position = Vector3.zero;
            instance.transform.rotation = Quaternion.Euler(0f, yaw, 0f);
            var bounds = GetBounds(instance);
            var scale = height / Mathf.Max(.001f, bounds.size.y);
            instance.transform.localScale *= scale;
            instance.transform.position = position - Vector3.up * bounds.min.y * scale;
            foreach (var collider in instance.GetComponentsInChildren<Collider>(true)) collider.enabled = false;
            return instance;
        }

        private static Bounds GetBounds(GameObject instance)
        {
            var renderers = instance.GetComponentsInChildren<Renderer>();
            if (renderers.Length == 0) return new Bounds(Vector3.zero, Vector3.one);
            var bounds = renderers[0].bounds;
            foreach (var renderer in renderers.Skip(1)) bounds.Encapsulate(renderer.bounds);
            return bounds;
        }

        private static GameObject Shape(string name, PrimitiveType type, Vector3 position, Vector3 scale, Material material, Transform parent, bool collision)
        {
            var instance = GameObject.CreatePrimitive(type);
            instance.name = name;
            instance.transform.SetParent(parent, true);
            instance.transform.position = position;
            instance.transform.localScale = scale;
            instance.GetComponent<Renderer>().sharedMaterial = material;
            instance.GetComponent<Collider>().enabled = collision;
            return instance;
        }

        private static void Disc(string name, Vector3 position, float radius, Material material, Transform parent)
        {
            Shape(name, PrimitiveType.Cylinder, position, new Vector3(radius * 2f, .012f, radius * 2f), material, parent, false);
        }

    }
}
