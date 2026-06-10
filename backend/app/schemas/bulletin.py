from pydantic import BaseModel, Field, model_validator


class BulletinPreferenceRequest(BaseModel):
    selection_type: str
    cluster_ids: list[int] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)
    include_digests: bool = True
    notifications_enabled: bool = True

    @model_validator(mode="after")
    def validate_selection(self):
        if self.selection_type not in {"clusters", "categories"}:
            raise ValueError("selection_type must be 'clusters' or 'categories'.")
        if self.selection_type == "clusters" and not self.cluster_ids:
            raise ValueError("At least one cluster must be selected.")
        if self.selection_type == "categories" and not self.categories:
            raise ValueError("At least one category must be selected.")
        return self
