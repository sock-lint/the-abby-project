using System;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif
using UnityEngine;
using UnityEngine.UI;

namespace AbbyCamp.UI
{
    /// <summary>Uses CSS pixels on Web and a 390-unit short edge in native/editor views.
    /// Insets follow the device safe area. A native keyboard reduces the usable area;
    /// browser keyboard resizing is handled by the same screen-size observation.</summary>
    public sealed class CampPhoneLayout : MonoBehaviour
    {
        public const float ReferenceShortEdge = 390f;
        private Canvas uiCanvas;
        private CanvasScaler scaler;
        private RectTransform safeRoot;
        private Rect previousUsable;
        private Vector2Int previousScreen;
        private Vector2Int previousLayoutScreen;
        private Vector2Int referenceScreen;
        private bool keyboardResize;
        private float previousScale;

#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] private static extern double AbbyDisplay_GetPixelsPerCssPixel();
#endif

        // Read the actual canvas ratio, rather than the requested browser DPR:
        // rounding and an in-progress resize can make those values differ.
        public static float GetUiScale(Vector2Int referenceScreen)
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            double scale = AbbyDisplay_GetPixelsPerCssPixel();
            return scale > 0 && !double.IsNaN(scale) && !double.IsInfinity(scale) ? (float)scale : 1f;
#else
            return Mathf.Min(referenceScreen.x, referenceScreen.y) / ReferenceShortEdge;
#endif
        }

        public static float TapMovementThreshold()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            float scale = GetUiScale(new Vector2Int(Screen.width, Screen.height));
            return Mathf.Clamp(Screen.width / scale * .035f, 12f, 28f) * scale;
#else
            return Mathf.Clamp(Screen.width * .035f, 12f, 28f);
#endif
        }

        public event Action LayoutChanged;
        public Rect UsableScreenRect { get; private set; }
        public Vector2 LogicalSize => safeRoot == null ? Vector2.zero : safeRoot.rect.size;
        public bool IsLandscape => referenceScreen.x > referenceScreen.y;

        public void Configure(Canvas canvas, CanvasScaler canvasScaler, RectTransform root)
        {
            uiCanvas = canvas;
            scaler = canvasScaler;
            safeRoot = root;
            Apply(true);
        }

        private void Update() => Apply(false);

        private void Apply(bool force)
        {
            if (safeRoot == null || Screen.width <= 0 || Screen.height <= 0) return;
            var screen = new Vector2Int(Screen.width, Screen.height);
            var usable = Screen.safeArea;
            if (usable.width <= 0 || usable.height <= 0)
                usable = new Rect(0, 0, Screen.width, Screen.height);
            // Some platforms already resize the screen for the keyboard. Only apply
            // an inset when Unity reports a keyboard area inside the current screen.
            var keyboard = TouchScreenKeyboard.area;
            if (TouchScreenKeyboard.visible && keyboard.height > 0 && keyboard.yMax < Screen.height)
            {
                var bottom = Mathf.Max(usable.yMin, keyboard.yMax);
                if (bottom < usable.yMax) usable.yMin = bottom;
            }
            float observedScale = GetUiScale(referenceScreen == Vector2Int.zero ? screen : referenceScreen);
            if (!force && screen == previousScreen && usable == previousUsable
                && Mathf.Approximately(observedScale, previousScale)) return;
#if UNITY_WEBGL && !UNITY_EDITOR
            // Density changes are not rotations. Remember the full viewport in
            // CSS units so a DPR change while typing preserves its orientation.
            var layoutScreen = new Vector2Int(Mathf.RoundToInt(screen.x / observedScale),
                Mathf.RoundToInt(screen.y / observedScale));
#else
            var layoutScreen = screen;
#endif
            bool inputFocused = false;
            foreach (var input in uiCanvas.GetComponentsInChildren<InputField>())
                if (input.isFocused) { inputFocused = true; break; }
            if (force || referenceScreen == Vector2Int.zero)
            {
                referenceScreen = layoutScreen;
                keyboardResize = false;
            }
            else if (layoutScreen.x != previousLayoutScreen.x)
            {
                // If rotated while typing, the browser may still report the
                // keyboard-reduced height. The old width is the new full height.
                referenceScreen = inputFocused || TouchScreenKeyboard.visible || keyboardResize
                    ? new Vector2Int(layoutScreen.x, Mathf.Max(layoutScreen.y, referenceScreen.x))
                    : layoutScreen;
                keyboardResize = layoutScreen.y < referenceScreen.y;
            }
            else if (inputFocused || TouchScreenKeyboard.visible)
            {
                keyboardResize = layoutScreen.y < referenceScreen.y;
            }
            else if (!keyboardResize || layoutScreen.y >= referenceScreen.y)
            {
                referenceScreen = layoutScreen;
                keyboardResize = false;
            }
            // Preserve the original touch scale while the browser keyboard reduces
            // visualViewport height, including its close animation after blur.
            previousScreen = screen;
            previousLayoutScreen = layoutScreen;
            previousUsable = usable;
            UsableScreenRect = usable;
            // More render pixels improve clarity without changing CSS-sized
            // controls, text, scrolling or the logical portrait/landscape layout.
            float scale = GetUiScale(referenceScreen);
            previousScale = scale;
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ConstantPixelSize;
            scaler.scaleFactor = scale;
            uiCanvas.scaleFactor = scale;
            safeRoot.anchorMin = new Vector2(usable.xMin / Screen.width, usable.yMin / Screen.height);
            safeRoot.anchorMax = new Vector2(usable.xMax / Screen.width, usable.yMax / Screen.height);
            safeRoot.offsetMin = Vector2.zero;
            safeRoot.offsetMax = Vector2.zero;
            Canvas.ForceUpdateCanvases();
            LayoutChanged?.Invoke();
        }
    }
}
