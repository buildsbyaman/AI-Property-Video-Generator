import io
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app
from app.validators import parse_and_validate_property_data, validate_and_filter_images


def create_dummy_image_bytes(format="JPEG", size=(100, 100), color="blue") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format)
    return buf.getvalue()


def test_property_validation_valid():
    data = {
        "property_name": "Sunset Heights Villa",
        "location": "North Goa, India",
        "price": "₹2.5 Crore",
        "property_type": "Villa",
        "bedrooms": "4 BHK",
        "area": "3,200 sq ft",
        "key_features": ["Private Pool", "Sea View", "Italian Marble Flooring"],
        "contact_cta": "Call +91 98765 43210 or visit sunsetheights.com",
        "voiceover_enabled": True,
        "script_mode": "template",
    }
    prop_input, errors = parse_and_validate_property_data(data)
    assert errors == []
    assert prop_input is not None
    assert prop_input.property_name == "Sunset Heights Villa"
    assert prop_input.bedrooms == "4 BHK"
    assert len(prop_input.key_features) == 3


def test_property_validation_missing_required():
    data = {
        "property_name": "A",  # too short (< 2)
        "location": "",         # empty (< 2)
        "price": "",            # empty
        "property_type": "InvalidType",
        "key_features": ["Only one"],  # less than 3
        "contact_cta": "",
    }
    prop_input, errors = parse_and_validate_property_data(data)
    assert prop_input is None
    error_fields = {e.field for e in errors}
    assert "property_name" in error_fields
    assert "location" in error_fields
    assert "price" in error_fields
    assert "property_type" in error_fields
    assert "key_features" in error_fields
    assert "contact_cta" in error_fields


def test_property_validation_optional_fields_clean():
    data = {
        "property_name": "Luxury Penthouse",
        "location": "Downtown Metropolis",
        "price": "$1,200,000",
        "property_type": "Apartment",
        "bedrooms": "   ",     # whitespace -> should become None
        "area": None,          # None -> None
        "key_features": ["Rooftop terrace\nConcierge 24/7\nPrivate elevator"],
        "contact_cta": "Schedule private viewing at penthouse.com",
    }
    prop_input, errors = parse_and_validate_property_data(data)
    assert errors == []
    assert prop_input is not None
    assert prop_input.bedrooms is None
    assert prop_input.area is None
    assert len(prop_input.key_features) == 3


def test_image_validation_count():
    dummy = create_dummy_image_bytes()

    # Case 1: Under 4 images
    files = [("img1.jpg", dummy, "image/jpeg"), ("img2.jpg", dummy, "image/jpeg")]
    valid, warnings, errors = validate_and_filter_images(files)
    assert len(errors) == 1
    assert errors[0].field == "images"
    assert "At least 4 images are required" in errors[0].message

    # Case 2: Exactly 4 valid images
    files_4 = [(f"img{i}.jpg", dummy, "image/jpeg") for i in range(4)]
    valid, warnings, errors = validate_and_filter_images(files_4)
    assert errors == []
    assert len(valid) == 4

    # Case 3: More than 8 images (e.g. 10 images)
    files_10 = [(f"img{i}.jpg", dummy, "image/jpeg") for i in range(10)]
    valid, warnings, errors = validate_and_filter_images(files_10)
    assert errors == []
    assert len(valid) == 8
    assert any("first 8 will be used" in w for w in warnings)


def test_image_validation_corrupt_and_size():
    valid_bytes = create_dummy_image_bytes()
    corrupt_bytes = b"not_a_real_image_data_here"

    # 4 valid + 1 corrupt -> 4 valid remain, warning issued, no error
    files = [(f"img{i}.jpg", valid_bytes, "image/jpeg") for i in range(4)]
    files.append(("corrupt.jpg", corrupt_bytes, "image/jpeg"))

    valid, warnings, errors = validate_and_filter_images(files)
    assert errors == []
    assert len(valid) == 4
    assert any("corrupt or unreadable" in w for w in warnings)

    # 3 valid + 1 corrupt -> only 3 remain -> error
    files_under = [(f"img{i}.jpg", valid_bytes, "image/jpeg") for i in range(3)]
    files_under.append(("corrupt.jpg", corrupt_bytes, "image/jpeg"))

    valid, warnings, errors = validate_and_filter_images(files_under)
    assert len(errors) == 1
    assert "Only 3 valid image(s) could be read" in errors[0].message


@pytest.mark.asyncio
async def test_api_generate_success_and_status():
    dummy = create_dummy_image_bytes()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Prepare multipart files
        files = [
            ("images", (f"photo_{i}.jpg", dummy, "image/jpeg"))
            for i in range(5)
        ]
        data = {
            "property_name": "Skyline Heights",
            "location": "Bandra West, Mumbai",
            "price": "₹4.2 Crore",
            "property_type": "Apartment",
            "bedrooms": "3 BHK",
            "area": "1,650 sq ft",
            "key_features": "Sea Facing Balcony\nModular Kitchen\nCovered Car Parking",
            "contact_cta": "Call 9820098200 to schedule a visit",
            "voiceover_enabled": "true",
            "script_mode": "template",
        }

        response = await client.post("/api/generate", data=data, files=files)
        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert body["status"] == "queued"

        job_id = body["job_id"]

        # Check GET /api/jobs/{job_id}
        status_res = await client.get(f"/api/jobs/{job_id}")
        assert status_res.status_code == 200
        status_body = status_res.json()
        assert status_body["job_id"] == job_id
        assert status_body["status"] == "queued"


@pytest.mark.asyncio
async def test_api_generate_validation_failure():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Invalid: missing required fields and only 1 image
        dummy = create_dummy_image_bytes()
        files = [("images", ("photo.jpg", dummy, "image/jpeg"))]
        data = {
            "property_name": "",
            "location": "",
            "price": "",
            "property_type": "",
            "key_features": "",
            "contact_cta": "",
        }

        response = await client.post("/api/generate", data=data, files=files)
        assert response.status_code == 422
        body = response.json()
        assert "errors" in body
        error_fields = [e["field"] for e in body["errors"]]
        assert "property_name" in error_fields
        assert "location" in error_fields
        assert "images" in error_fields
