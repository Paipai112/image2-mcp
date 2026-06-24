import pytest
from pydantic import ValidationError
from image2_mcp.schemas import VALID_SIZES, GenerateImageInput, ImageOutput


def test_valid_sizes_contains_presets():
    for size in ("1024x1024", "1536x1024", "1024x1536", "2048x2048",
                  "2048x1152", "3840x2160", "2160x3840", "auto"):
        assert size in VALID_SIZES


def test_custom_size_valid():
    """Custom sizes must pass structural rules."""
    input_data = GenerateImageInput(prompt="test", size="2048x1280")
    assert input_data.size == "2048x1280"


def test_custom_size_not_multiple_of_16():
    with pytest.raises(ValidationError, match="multiple of 16"):
        GenerateImageInput(prompt="test", size="100x100")


def test_custom_size_max_dimension_exceeded():
    with pytest.raises(ValidationError, match="max 3840px"):
        GenerateImageInput(prompt="test", size="4096x4096")


def test_custom_size_aspect_ratio_exceeded():
    with pytest.raises(ValidationError, match="3:1"):
        GenerateImageInput(prompt="test", size="3840x960")  # 4:1


def test_custom_size_total_pixels_too_low():
    with pytest.raises(ValidationError, match="655,360"):
        GenerateImageInput(prompt="test", size="640x640")


def test_custom_size_total_pixels_too_high():
    with pytest.raises(ValidationError, match="8,294,400"):
        GenerateImageInput(prompt="test", size="3840x2560")


def test_prompt_empty_string_rejected():
    with pytest.raises(ValidationError, match="prompt"):
        GenerateImageInput(prompt="", size="1024x1024")


def test_prompt_whitespace_only_rejected():
    with pytest.raises(ValidationError, match="prompt"):
        GenerateImageInput(prompt="   ", size="1024x1024")


def test_preset_size_no_custom_validation():
    """Preset sizes skip dimension validation."""
    input_data = GenerateImageInput(prompt="test", size="auto")
    assert input_data.size == "auto"


def test_quality_default_auto():
    input_data = GenerateImageInput(prompt="test", size="1024x1024")
    assert input_data.quality == "auto"


def test_quality_invalid_value_rejected():
    with pytest.raises(ValidationError, match="quality"):
        GenerateImageInput(prompt="test", size="1024x1024", quality="ultra")


def test_filename_default():
    input_data = GenerateImageInput(prompt="test", size="1024x1024")
    assert input_data.filename is None


def test_filename_custom():
    input_data = GenerateImageInput(prompt="test", size="1024x1024", filename="my_image")
    assert input_data.filename == "my_image"


def test_filename_with_path_separators():
    input_data = GenerateImageInput(prompt="test", size="1024x1024", filename="dir/my_image")
    assert input_data.filename == "dir_my_image"


def test_filename_whitespace_only():
    input_data = GenerateImageInput(prompt="test", size="1024x1024", filename="   ")
    assert input_data.filename is None


def test_size_invalid_format():
    with pytest.raises(ValidationError, match="Invalid size format"):
        GenerateImageInput(prompt="test", size="not-a-size")


def test_image_output_model():
    output = ImageOutput(path="/tmp/out.png", usage={"total_tokens": 100})
    assert output.path == "/tmp/out.png"
    assert output.url == "file:///tmp/out.png"
    assert output.usage == {"total_tokens": 100}
