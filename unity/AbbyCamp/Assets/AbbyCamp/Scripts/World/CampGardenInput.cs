using System;
using System.Collections.Generic;
using AbbyCamp.Presentation;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace AbbyCamp.World
{
    /// <summary>Accepts a deliberate companion tap; scenery never starts movement.</summary>
    public sealed class CampGardenInput : MonoBehaviour
    {
        [SerializeField] private CompanionFollower companion;
        private bool inputEnabled = true;
        private int activeFinger = -1;
        private Vector2 pointerStart;
        private float pointerStartedAt;
        private float suppressMouseUntil;
        private bool mouseTap;
        private readonly List<RaycastResult> interfaceHits = new List<RaycastResult>();

        public event Action CompanionTapped;
        public CompanionFollower Companion => companion;
        public bool InputEnabled => inputEnabled;

        public void Configure(CompanionFollower pet) => companion = pet;

        public void SetInputEnabled(bool enabled)
        {
            inputEnabled = enabled;
            ResetPointer();
        }

        private void OnDisable() => ResetPointer();
        private void OnApplicationFocus(bool focused) { if (!focused) ResetPointer(); }
        private void ResetPointer() { activeFinger = -1; mouseTap = false; }

        private void Update()
        {
            if (!inputEnabled) return;
            // Some browsers synthesize mouse-up after touch-end. Suppress that
            // entire tail, including the first frame with no remaining touches.
            if (Input.touchCount > 0)
            {
                suppressMouseUntil = Time.unscaledTime + .6f;
                mouseTap = false;
                if (Input.touchCount > 1) { activeFinger = -1; return; }
                var touch = Input.GetTouch(0);
                if (touch.phase == TouchPhase.Began)
                {
                    activeFinger = PointerHitsInterface(touch.position) ? -1 : touch.fingerId;
                    BeginPointer(touch.position);
                }
                else if (touch.fingerId == activeFinger && touch.phase == TouchPhase.Ended)
                {
                    activeFinger = -1;
                    if (IsTap(touch.position)) TryTapCompanion(touch.position);
                }
                else if (touch.phase == TouchPhase.Canceled) activeFinger = -1;
                return;
            }
            if (Time.unscaledTime < suppressMouseUntil) { ResetPointer(); return; }
            if (Input.GetMouseButtonDown(0))
            {
                mouseTap = !PointerHitsInterface(Input.mousePosition);
                BeginPointer(Input.mousePosition);
            }
            if (Input.GetMouseButtonUp(0))
            {
                bool accepted = mouseTap;
                mouseTap = false;
                if (accepted && IsTap(Input.mousePosition)) TryTapCompanion(Input.mousePosition);
            }
        }

        private void BeginPointer(Vector2 position)
        {
            pointerStart = position;
            pointerStartedAt = Time.unscaledTime;
        }

        private bool IsTap(Vector2 position) => Time.unscaledTime - pointerStartedAt <= .75f
            && (position - pointerStart).sqrMagnitude <= Mathf.Pow(AbbyCamp.UI.CampPhoneLayout.TapMovementThreshold(), 2f);

        private bool PointerHitsInterface(Vector2 position)
        {
            if (EventSystem.current == null) return false;
            interfaceHits.Clear();
            EventSystem.current.RaycastAll(new PointerEventData(EventSystem.current) { position = position }, interfaceHits);
            foreach (var hit in interfaceHits)
                if (hit.module is GraphicRaycaster) return true;
            return false;
        }

        // Models and public portrait fallbacks share the same visible-bounds
        // interaction. No collider, ground plane, destination or proximity gate.
        public bool TryTapCompanion(Vector2 screenPosition)
        {
            var view = Camera.main;
            if (!inputEnabled || !isActiveAndEnabled || companion == null || view == null
                || screenPosition.x < 0f || screenPosition.y < 0f
                || screenPosition.x > Screen.width || screenPosition.y > Screen.height
                || PointerHitsInterface(screenPosition)) return false;
            var appearance = companion.GetComponent<VisualPresenter>();
            if (appearance == null) return false;
            var ray = view.ScreenPointToRay(screenPosition);
            foreach (Transform visual in appearance.transform)
            {
                // A swap can leave an inactive old Appearance until the end of
                // the frame. Reward particles are separate children, not taps.
                if (visual.name != "Appearance" || !visual.gameObject.activeInHierarchy) continue;
                foreach (var renderer in visual.GetComponentsInChildren<Renderer>())
                {
                    if (!renderer.enabled || !renderer.gameObject.activeInHierarchy
                        || !renderer.bounds.IntersectRay(ray, out var distance)
                        || distance < 0f || distance > view.farClipPlane) continue;
                    CompanionTapped?.Invoke();
                    return true;
                }
            }
            return false;
        }
    }
}
