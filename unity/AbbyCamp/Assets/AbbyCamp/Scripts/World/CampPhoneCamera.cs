using UnityEngine;

namespace AbbyCamp.World
{
    /// <summary>A fixed companion view, framed around the responsive Play controls.</summary>
    [RequireComponent(typeof(Camera))]
    public sealed class CampPhoneCamera : MonoBehaviour
    {
        [SerializeField] private Transform subject;
        [SerializeField] private float portraitWorldHeight = 4.6f;
        [SerializeField] private float landscapeWorldHeight = 3.2f;
        [SerializeField] private Vector3 framingOffset = new Vector3(0f, .95f, 0f);
        private Camera view;
        private int framedWidth;
        private int framedHeight;
        private Rect framedSafeArea;
        private float framedAspect;
        private float framedUiScale;

        public Transform Subject => subject;

        public void Configure(Transform companion)
        {
            subject = companion;
            RefreshFraming();
        }

        public void ConfigureFraming(float visibleHeight, Vector3 focusOffset)
        {
            portraitWorldHeight = Mathf.Clamp(visibleHeight, 3.4f, 6.8f);
            framingOffset = focusOffset;
            if (subject != null) RefreshFraming();
        }

        private void Start()
        {
            view = GetComponent<Camera>();
            if (subject == null) subject = FindFirstObjectByType<CompanionFollower>()?.transform;
            RefreshFraming();
            Application.targetFrameRate = 30;
        }

        private void LateUpdate()
        {
            if (view == null || subject == null) return;
            if (Screen.width != framedWidth || Screen.height != framedHeight
                || Screen.safeArea != framedSafeArea || Mathf.Abs(view.aspect - framedAspect) > .0001f
                || !Mathf.Approximately(AbbyCamp.UI.CampPhoneLayout.GetUiScale(
                    new Vector2Int(Screen.width, Screen.height)), framedUiScale))
                RefreshFraming();
        }

        public void RefreshFraming()
        {
            if (view == null) view = GetComponent<Camera>();
            if (view == null || subject == null) return;
            float width = Mathf.Max(1, Screen.width);
            float height = Mathf.Max(1, Screen.height);
            var safe = Screen.safeArea;
            if (safe.width <= 0f || safe.height <= 0f) safe = new Rect(0f, 0f, width, height);
            bool portrait = height >= width;
            float uiScale = AbbyCamp.UI.CampPhoneLayout.GetUiScale(new Vector2Int(Screen.width, Screen.height));
            float bottom = (portrait ? 248f : 80f) * uiScale;
            float margin = 12f * uiScale;
            // Match the home controls' logical size at every render density.
            float right = portrait ? 0f : Mathf.Min(350f, (safe.width / uiScale - 24f) * .45f) * uiScale;
            var available = new Rect(safe.x + margin, safe.y + bottom,
                Mathf.Max(80f * uiScale, safe.width - right - 2f * margin),
                Mathf.Max(80f * uiScale, safe.height - 124f * uiScale - bottom));
            float visibleHeight = portrait ? portraitWorldHeight : landscapeWorldHeight;
            float aspect = Mathf.Max(.1f, view.aspect);
            // Keep the complete hero (including its local hop) inside the free
            // region, with a little woodland beside it even on narrow phones.
            view.orthographicSize = Mathf.Max(visibleHeight * height / (2f * available.height),
                3.2f * width / (2f * available.width * aspect));
            var desiredCenter = new Vector2(available.center.x / width, available.center.y / height);
            var focus = subject.position + framingOffset
                + transform.right * ((.5f - desiredCenter.x) * 2f * view.orthographicSize * aspect)
                + transform.up * ((.5f - desiredCenter.y) * 2f * view.orthographicSize);
            // Subject animation is local to Appearance. Greeting, rewards and
            // modal transitions never move this camera or its gameplay anchor.
            transform.position = focus - transform.forward * 24f;
            framedWidth = Screen.width;
            framedHeight = Screen.height;
            framedSafeArea = Screen.safeArea;
            framedAspect = view.aspect;
            framedUiScale = uiScale;
        }
    }
}
