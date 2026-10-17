"""Bounded template authoring inputs; original schema imports remain compatible."""
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .schemas import (
    CreateProjectFromTemplateIn as OriginalCreateProjectFromTemplateIn,
    CreateTemplateIn as OriginalCreateTemplateIn,
    DeleteTemplateIn as DeleteTemplateIn,
    GetTemplateIn as GetTemplateIn,
    ListTemplatesIn as ListTemplatesIn,
    NewMilestoneSkillTag, NewProjectSkillTag,
    SaveProjectAsTemplateIn as OriginalSaveProjectAsTemplateIn,
    TemplateMaterialDraft as OriginalTemplateMaterialDraft, TemplateResourceDraft, TemplateStepDraft,
    TemplateMilestoneDraft as OriginalTemplateMilestoneDraft,
    UpdateTemplateIn as OriginalUpdateTemplateIn,
)


class TemplateMaterialDraft(OriginalTemplateMaterialDraft):
    estimated_cost: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=8, decimal_places=2)


class TemplateMilestoneDraft(OriginalTemplateMilestoneDraft):
    bonus_amount: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    skill_tags: list[NewMilestoneSkillTag] = Field(default_factory=list, max_length=50)


class CreateTemplateIn(OriginalCreateTemplateIn):
    bonus_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=8, decimal_places=2)
    materials_budget: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=8, decimal_places=2)
    request_id: UUID | None = Field(default=None, description="Stable UUID for duplicate-safe retries; reuse only with identical inputs.")
    skill_tags: list[NewProjectSkillTag] = Field(default_factory=list, max_length=50)
    milestones: list[TemplateMilestoneDraft] = Field(default_factory=list, max_length=100)
    materials: list[TemplateMaterialDraft] = Field(default_factory=list, max_length=200)
    steps: list[TemplateStepDraft] = Field(default_factory=list, max_length=300)
    resources: list[TemplateResourceDraft] = Field(default_factory=list, max_length=300)


class UpdateTemplateIn(OriginalUpdateTemplateIn):
    bonus_amount: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    materials_budget: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    skill_tags: list[NewProjectSkillTag] | None = Field(default=None, max_length=50)
    milestones: list[TemplateMilestoneDraft] | None = Field(default=None, max_length=100)
    materials: list[TemplateMaterialDraft] | None = Field(default=None, max_length=200)
    steps: list[TemplateStepDraft] | None = Field(default=None, max_length=300)
    resources: list[TemplateResourceDraft] | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_replacement(self):
        nested = {"milestones", "materials", "steps", "resources"}
        supplied = nested.intersection(self.model_fields_set)
        if supplied and (supplied != nested or any(getattr(self, field) is None for field in nested)):
            raise ValueError("Structural editing requires all four arrays: milestones, materials, steps, resources; use [] to clear.")
        for field in self.model_fields_set - {"category_id", "instructables_url"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null; omit it to keep the saved value.")
        return self


class SaveProjectAsTemplateIn(OriginalSaveProjectAsTemplateIn):
    request_id: UUID | None = Field(default=None, description="Stable UUID for duplicate-safe retries with identical inputs.")


class CreateProjectFromTemplateIn(OriginalCreateProjectFromTemplateIn):
    request_id: UUID | None = Field(default=None, description="Stable UUID for duplicate-safe retries with identical inputs.")
    status: Literal["draft", "in_progress"] = Field(default="in_progress", description="Use draft to review the instantiated plan before starting it.")
