using AbbyCamp.Presentation;
using UnityEngine;

namespace AbbyCamp.World
{
    // Keep the component and gameplay identity while presentation moves from
    // following an avatar to a stationary, directly tappable companion.
    [RequireComponent(typeof(VisualPresenter))]
    public sealed class CompanionFollower : MonoBehaviour
    {
        [SerializeField] private VisualDefinition primaryAppearance;
        [SerializeField] private VisualDefinition secondaryAppearance;
        [SerializeField] private Vector3 anchorPosition;
        [SerializeField] private Quaternion anchorRotation = Quaternion.identity;

        public VisualPresenter Appearance => GetComponent<VisualPresenter>();
        public VisualDefinition PrimaryAppearance => primaryAppearance;
        public VisualDefinition SecondaryAppearance => secondaryAppearance;
        public Vector3 AnchorPosition => anchorPosition;
        public Quaternion AnchorRotation => anchorRotation;

        public void Configure(VisualDefinition first, VisualDefinition second)
        {
            primaryAppearance = first;
            secondaryAppearance = second;
            anchorPosition = transform.position;
            anchorRotation = transform.rotation;
            if (Appearance != null) Appearance.SetLocomotion(0f);
        }

        private void Awake() => RestoreAnchor();

        public void ApplyAppearance(VisualDefinition definition)
        {
            if (Appearance != null) Appearance.SetVisual(definition);
        }

        public void ToggleAppearance()
        {
            ApplyAppearance(Appearance != null && Appearance.Definition == secondaryAppearance ? primaryAppearance : secondaryAppearance);
        }

        public void Celebrate()
        {
            if (Appearance != null) Appearance.Celebrate();
        }

        private void LateUpdate()
        {
            RestoreAnchor();
            if (Appearance != null) Appearance.SetLocomotion(0f);
        }

        private void RestoreAnchor()
        {
            transform.SetPositionAndRotation(anchorPosition, anchorRotation);
        }
    }
}
