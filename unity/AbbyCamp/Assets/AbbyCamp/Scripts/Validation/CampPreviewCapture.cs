#if UNITY_EDITOR || DEVELOPMENT_BUILD
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;

namespace AbbyCamp.Validation
{
    /// <summary>Renders the real world and runtime UI independently of desktop-window visibility.</summary>
    public static class CampPreviewCapture
    {
        private const int Width = 1600;
        private const int Height = 900;

        private readonly struct CanvasState
        {
            public readonly Canvas Canvas;
            public readonly RenderMode Mode;
            public readonly Camera Camera;
            public readonly float PlaneDistance;

            public CanvasState(Canvas canvas)
            {
                Canvas = canvas;
                Mode = canvas.renderMode;
                Camera = canvas.worldCamera;
                PlaneDistance = canvas.planeDistance;
            }

            public void Restore()
            {
                if (Canvas == null) return;
                Canvas.renderMode = Mode;
                Canvas.worldCamera = Camera;
                Canvas.planeDistance = PlaneDistance;
            }
        }

        public static IEnumerator Capture(string path, int width = Width, int height = Height)
        {
            if (width < 64 || height < 64 || width > 4096 || height > 4096)
                throw new ArgumentOutOfRangeException(nameof(width), "Preview dimensions must be 64..4096 pixels.");
            var camera = UnityEngine.Camera.main;
            if (camera == null) throw new InvalidOperationException("Preview capture requires the camp camera.");
            if (SystemInfo.graphicsDeviceType == GraphicsDeviceType.Null)
                throw new InvalidOperationException("Preview capture requires an active graphics device.");
            var target = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
            {
                name = "Camp offscreen preview",
                antiAliasing = 1,
                useMipMap = false
            };
            target.Create();
            var originalTarget = camera.targetTexture;
            var originalAspect = camera.aspect;
            var originalActive = RenderTexture.active;
            var canvases = new List<CanvasState>();
            Texture2D image = null;

            try
            {
                camera.targetTexture = target;
                camera.aspect = (float)width / height;
                foreach (var canvas in UnityEngine.Object.FindObjectsByType<Canvas>(FindObjectsSortMode.None))
                {
                    if (!canvas.isActiveAndEnabled || !canvas.isRootCanvas || canvas.renderMode != RenderMode.ScreenSpaceOverlay) continue;
                    canvases.Add(new CanvasState(canvas));
                    canvas.renderMode = RenderMode.ScreenSpaceCamera;
                    canvas.worldCamera = camera;
                    canvas.planeDistance = Mathf.Max(1f, camera.nearClipPlane + .1f);
                }
                Canvas.ForceUpdateCanvases();
                // Let camera-space Canvas geometry/layout rebuild at the requested target resolution.
                yield return null;
                Canvas.ForceUpdateCanvases();
                ValidateLabelGeometry();
                var request = new UniversalRenderPipeline.SingleCameraRequest { destination = target };
                if (!RenderPipeline.SupportsRenderRequest(camera, request))
                    throw new InvalidOperationException("The active pipeline does not support an offscreen single-camera render.");
                RenderPipeline.SubmitRenderRequest(camera, request);
                RenderTexture.active = target;
                image = new Texture2D(width, height, TextureFormat.RGBA32, false, false);
                image.ReadPixels(new Rect(0, 0, width, height), 0, 0, false);
                image.Apply(false, false);
                ValidatePixels(image.GetPixels32(), Path.GetFileName(path), width, height);
                var absolutePath = Path.GetFullPath(path);
                Directory.CreateDirectory(Path.GetDirectoryName(absolutePath));
                File.WriteAllBytes(absolutePath, image.EncodeToPNG());
            }
            finally
            {
                foreach (var state in canvases) state.Restore();
                camera.targetTexture = originalTarget;
                camera.aspect = originalAspect;
                RenderTexture.active = originalActive;
                Canvas.ForceUpdateCanvases();
                if (image != null) UnityEngine.Object.Destroy(image);
                target.Release();
                UnityEngine.Object.Destroy(target);
            }
        }

        private static void ValidateLabelGeometry()
        {
            var names = new HashSet<string> { "CampTitle", "SheetTitle", "RewardStatus", "RewardBalance", "InboxStatus", "BestiaryStatus" };
            foreach (var text in UnityEngine.Object.FindObjectsByType<Text>(FindObjectsSortMode.None))
            {
                if (!names.Contains(text.name) || !text.isActiveAndEnabled || string.IsNullOrEmpty(text.text)) continue;
                var scroll = text.GetComponentInParent<ScrollRect>();
                if (scroll != null && scroll.viewport != null)
                {
                    var bounds = RectTransformUtility.CalculateRelativeRectTransformBounds(scroll.viewport, text.rectTransform);
                    var view = scroll.viewport.rect;
                    // A user can deliberately scroll a status out of view.
                    // Smoke checks its initial top position separately.
                    if (bounds.max.x <= view.xMin || bounds.min.x >= view.xMax
                        || bounds.max.y <= view.yMin || bounds.min.y >= view.yMax)
                    {
                        Debug.Log($"ABBY_PLAY_CAPTURE_TEXT_OFFSCREEN: {text.name}; rowBounds={bounds}, viewport={view}.");
                        continue;
                    }
                }
                // Unity 6 returns the renderer's borrowed mesh; its owner keeps it.
                var mesh = text.canvasRenderer.GetMesh();
                int vertices = mesh == null ? 0 : mesh.vertexCount;
                Debug.Log($"ABBY_PLAY_CAPTURE_TEXT: {text.name}; rect={text.rectTransform.rect}, preferredHeight={text.preferredHeight}, generatedVertices={text.cachedTextGenerator.vertexCount}, renderedVertices={vertices}, culled={text.canvasRenderer.cull}.");
                if (vertices == 0 || text.canvasRenderer.cull)
                    throw new InvalidOperationException("Preview text has no visible glyph mesh: " + text.name);
            }
        }

        private static void ValidatePixels(Color32[] pixels, string name, int width, int height)
        {
            var colors = new HashSet<int>();
            var sampleCount = 0;
            var brightCount = 0;
            var darkest = 255;
            var lightest = 0;
            for (var i = 0; i < pixels.Length; i += 7)
            {
                var pixel = pixels[i];
                var brightness = (pixel.r * 2 + pixel.g * 3 + pixel.b) / 6;
                darkest = Math.Min(darkest, brightness);
                lightest = Math.Max(lightest, brightness);
                if (brightness > 20) brightCount++;
                colors.Add((pixel.r >> 3) << 10 | (pixel.g >> 3) << 5 | (pixel.b >> 3));
                sampleCount++;
            }
            if (brightCount < sampleCount / 50 || lightest - darkest < 25 || colors.Count < 24)
                throw new InvalidOperationException($"Blank preview rejected: {name}; bright={brightCount}/{sampleCount}, range={lightest - darkest}, colors={colors.Count}.");
            Debug.Log($"ABBY_CAMP_PREVIEW_OK: {name}; {width}x{height}, bright={brightCount}/{sampleCount}, range={lightest - darkest}, colors={colors.Count}.");
        }
    }
}
#endif
