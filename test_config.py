"""Test script to verify dropdown selector works correctly."""
import voluptuous as vol
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SelectOptionDict,
)

# Test creating a simple dropdown selector
def test_dropdown_selector():
    """Test that dropdown selector can be created."""
    
    # Create some test options
    test_options = [
        SelectOptionDict(value="stop1", label="Stop 1 (stop1)"),
        SelectOptionDict(value="stop2", label="Stop 2 (stop2)"),
        SelectOptionDict(value="stop3", label="Stop 3 (stop3)"),
    ]
    
    # Create the data schema with dropdown
    data_schema = vol.Schema({
        vol.Required("selected_stops"): SelectSelector(
            SelectSelectorConfig(
                options=test_options,
                mode=SelectSelectorMode.DROPDOWN,
                multiple=True,
            )
        )
    })
    
    print("✅ Dropdown selector created successfully!")
    print(f"Options: {len(test_options)} items")
    print("Schema structure:", data_schema)
    
    return data_schema

if __name__ == "__main__":
    try:
        schema = test_dropdown_selector()
        print("\n✅ Test passed - dropdown selector works!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()