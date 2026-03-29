from copy import deepcopy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kedro_azureml_pipeline.utils import update_dict


class TestUpdateDict:
    """Tests for the ``update_dict`` helper."""

    @pytest.mark.parametrize(
        "input_dict, kv_pairs, expected_output",
        [
            ({}, [("a", 1)], {"a": 1}),
            ({"a": 1}, [("a", 2)], {"a": 2}),
            ({"a": {"b": 1}}, [("a.b", 2)], {"a": {"b": 2}}),
            ({"a": {"b": {"c": 1}}}, [("a.b.c", 2)], {"a": {"b": {"c": 2}}}),
            (
                {"a": {"b": {"c": 1}}},
                [("a.b.c", 2), ("a.b.d", 3)],
                {"a": {"b": {"c": 2, "d": 3}}},
            ),
            ({}, [("a.b.c", 1)], {"a": {"b": {"c": 1}}}),
        ],
    )
    def test_returns_expected_output(self, input_dict, kv_pairs, expected_output):
        """Verify that the dict is updated correctly for various key paths."""
        actual_output = update_dict(input_dict, *kv_pairs)
        assert actual_output == expected_output

    def test_returns_deep_copy(self):
        """Result must be a new dict, not the original."""
        original = {"a": 1}
        result = update_dict(original, ("a", 2))
        assert result is not original

    def test_does_not_mutate_input(self):
        """The source dictionary must remain unchanged."""
        original = {"a": {"b": 1}}
        copied = deepcopy(original)
        update_dict(original, ("a.b", 2))
        assert original == copied

    def test_overwrites_non_dict_intermediate_with_nested_key(self):
        """A scalar at an intermediate key should be replaced by a dict."""
        result = update_dict({"a": 1}, ("a.b", 2))
        assert result == {"a": {"b": 2}}

    def test_no_pairs_returns_copy(self):
        """Calling with no kv_pairs returns an unmodified deep copy."""
        original = {"x": [1, 2]}
        result = update_dict(original)
        assert result == original
        assert result is not original

    @given(
        key=st.text(
            alphabet=st.sampled_from("abcdefghij."),
            min_size=1,
            max_size=10,
        ).filter(lambda s: not s.startswith(".") and not s.endswith(".") and ".." not in s),
        value=st.integers(),
    )
    def test_always_returns_new_dict_with_key_set(self, key, value):
        """Property: update_dict always produces a new dict containing the key."""
        result = update_dict({}, (key, value))
        assert result is not None
        # Walk into the nested result to verify the leaf value
        parts = key.split(".")
        node = result
        for part in parts:
            assert part in node
            node = node[part]
        assert node == value
