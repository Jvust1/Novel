"""Novel AI writing assistant core package."""

__version__ = "0.12.0-dev"

from .oss_batch_20261004 import (
    OSSProject as ValidatedOSSProject,
    PROJECTS as VALIDATED_OSS_PROJECTS,
    RUNTIME_TARGETS as VALIDATED_RUNTIME_TARGETS,
    adoption_plan as validated_oss_adoption_plan,
    available_projects as available_validated_oss_projects,
    choose_backend as choose_validated_oss_backend,
    choose_recall_backend as choose_validated_oss_recall_backend,
    list_projects as list_validated_oss_projects,
)

__all__ = [
    "ValidatedOSSProject",
    "VALIDATED_OSS_PROJECTS",
    "VALIDATED_RUNTIME_TARGETS",
    "validated_oss_adoption_plan",
    "available_validated_oss_projects",
    "choose_validated_oss_backend",
    "choose_validated_oss_recall_backend",
    "list_validated_oss_projects",
]
