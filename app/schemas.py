"""Pydantic schemas and validation models for AI Property Video Generator."""

from enum import Enum
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class PropertyType(str, Enum):
    APARTMENT = "Apartment"
    VILLA = "Villa"
    HOUSE = "House"
    PLOT = "Plot"
    COMMERCIAL = "Commercial"
    OTHER = "Other"


class ScriptMode(str, Enum):
    TEMPLATE = "template"
    AI = "ai"


class JobStatus(str, Enum):
    QUEUED = "queued"
    SCRIPTING = "scripting"
    NARRATING = "narrating"
    RENDERING = "rendering"
    DONE = "done"
    ERROR = "error"


class FieldError(BaseModel):
    field: str
    message: str


class ValidationErrorResponse(BaseModel):
    errors: List[FieldError]


class PropertyInput(BaseModel):
    property_name: str = Field(..., description="Name of the property (2-80 chars)")
    location: str = Field(..., description="Location of the property (2-120 chars)")
    price: str = Field(..., description="Property price (free text e.g. ₹85 Lakh, $450,000)")
    property_type: PropertyType = Field(..., description="Type of property")
    bedrooms: Optional[str] = Field(None, description="Bedrooms or configuration e.g. 2 BHK")
    area: Optional[str] = Field(None, description="Total area e.g. 1,050 sq ft")
    key_features: List[str] = Field(..., description="List of 3 to 8 key features")
    contact_cta: str = Field(..., description="Call to action text / contact info")
    voiceover_enabled: bool = Field(True, description="Whether voiceover narration is enabled")
    script_mode: ScriptMode = Field(ScriptMode.TEMPLATE, description="Script generation mode")

    @field_validator("property_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip() if isinstance(v, str) else ""
        if len(s) < 2 or len(s) > 80:
            raise ValueError("Property name must be between 2 and 80 characters")
        return s

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: str) -> str:
        s = v.strip() if isinstance(v, str) else ""
        if len(s) < 2 or len(s) > 120:
            raise ValueError("Location must be between 2 and 120 characters")
        return s

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: str) -> str:
        s = v.strip() if isinstance(v, str) else ""
        if not s or len(s) > 60:
            raise ValueError("Price must be specified and under 60 characters")
        return s

    @field_validator("bedrooms", "area")
    @classmethod
    def clean_optional_strings(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s if s else None

    @field_validator("key_features")
    @classmethod
    def validate_features(cls, v: Any) -> List[str]:
        raw_list = []
        if isinstance(v, str):
            raw_list = [line.strip() for line in v.splitlines() if line.strip()]
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    for line in item.splitlines():
                        s = line.strip()
                        if s:
                            raw_list.append(s)
                elif item:
                    s = str(item).strip()
                    if s:
                        raw_list.append(s)

        if len(raw_list) < 3:
            raise ValueError("At least 3 key features are required")
        if len(raw_list) > 8:
            raise ValueError("A maximum of 8 key features is allowed")
        return raw_list

    @field_validator("contact_cta")
    @classmethod
    def validate_cta(cls, v: str) -> str:
        s = v.strip() if isinstance(v, str) else ""
        if len(s) < 2 or len(s) > 150:
            raise ValueError("Contact / CTA text must be between 2 and 150 characters")
        return s


class Scene(BaseModel):
    type: Literal["title", "feature", "details", "cta"]
    image_index: int = Field(..., ge=0)
    caption: str = Field(..., description="Short caption (<= 8 words per line)")
    voiceover: Optional[str] = Field(None, description="Narration text (<= 25 words)")


class ScriptOutput(BaseModel):
    scenes: List[Scene]
    used_template_fallback: bool = False


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = Field(0, ge=0, le=100)
    message: str = ""
    warnings: List[str] = Field(default_factory=list)
    video_url: Optional[str] = None
    script: Optional[ScriptOutput] = None
