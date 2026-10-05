"""
Type aliases used across the config package.
"""

# key -> (allowed types, required)
FieldSpec = tuple[tuple[type, ...], bool]
