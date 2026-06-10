from pydantic import BaseModel, Field, root_validator


class BulletinPreferenceRequest(BaseModel):
    selection_type: str
    cluster_ids: list[int] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=50)
    include_digests: bool = True
    notifications_enabled: bool = True

    @root_validator(skip_on_failure=True)
    def validate_selection(cls, values):
        selection_type = values.get("selection_type")
        cluster_ids = values.get("cluster_ids") or []
        categories = values.get("categories") or []
        if selection_type not in {"clusters", "categories"}:
            raise ValueError("selection_type must be 'clusters' or 'categories'.")
        if selection_type == "clusters" and not cluster_ids:
            raise ValueError("At least one cluster must be selected.")
        if selection_type == "categories" and not categories:
            raise ValueError("At least one category must be selected.")
        return values
