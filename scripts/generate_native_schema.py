#!/usr/bin/env python3
"""Generate deterministic native TDLibKit schema IR from pinned td_api.tl.

The TL file is the schema source of truth. Type IDs are read from TDLib's own
generated td_api.h after `tdlib-native.sh generate` has derived it from that TL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from native_versions import read_versions, verify_source


ROOT = Path(__file__).resolve().parent.parent
TL_PATH = ROOT / "Vendor/td/td/generate/scheme/td_api.tl"
HEADER_PATH = ROOT / "Vendor/td/td/generate/auto/td/telegram/td_api.h"
DEFAULT_OUTPUT = ROOT / "Native/Generated/schema.json"
DEFAULT_ACCESS_OUTPUT = ROOT / "Sources/TDLibCxxBridge/Generated/SchemaAccess.inc"
DEFAULT_SWIFT_OUTPUT = ROOT / "Sources/TDLibKitNative/Generated/SchemaViews.swift"
DEFAULT_FACTORY_OUTPUT = ROOT / "Sources/TDLibCxxBridge/Generated/SchemaFactory.inc"
PINNED_COMMIT = read_versions()["tdlib_commit"]
PRIMITIVES = {"Bool", "bytes", "double", "int32", "int53", "int64", "string"}
BUILTIN_DECLARATIONS = {
    "double",
    "string",
    "int32",
    "int53",
    "int64",
    "bytes",
    "boolFalse",
    "boolTrue",
    "vector",
}
DECLARATION_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)(.*?) = ([A-Za-z][A-Za-z0-9_]*);$")
FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*):(.+)$")
DOC_TAG_RE = re.compile(
    r"@([a-z][a-z0-9_]*)\s+(.*?)(?=\s+@[a-z][a-z0-9_]*\s|$)"
)
CLASS_ID_RE = re.compile(
    r"class\s+([A-Za-z][A-Za-z0-9_]*)\s+final\s*:\s*public\s+[A-Za-z][A-Za-z0-9_]*\s*\{"
    r".*?static const std::int32_t ID = (-?[0-9]+);",
    re.DOTALL,
)


@dataclass(frozen=True)
class TypeRef:
    kind: str
    name: str | None = None
    element: "TypeRef | None" = None

    def json(self) -> dict[str, object]:
        result: dict[str, object] = {"kind": self.kind}
        if self.name is not None:
            result["name"] = self.name
        if self.element is not None:
            result["element"] = self.element.json()
        return result


@dataclass(frozen=True)
class Field:
    name: str
    type_ref: TypeRef
    is_optional: bool

    def json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.type_ref.json(),
            "is_optional": self.is_optional,
        }


@dataclass(frozen=True)
class Declaration:
    name: str
    result: str
    fields: tuple[Field, ...]
    is_function: bool
    type_id: int

    def json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "result": self.result,
            "fields": [field.json() for field in self.fields],
            "is_function": self.is_function,
            "type_id": self.type_id,
        }


def parse_type(text: str) -> TypeRef:
    if text.startswith("vector<") and text.endswith(">"):
        return TypeRef(kind="vector", element=parse_type(text[7:-1]))
    if text in PRIMITIVES:
        return TypeRef(kind="primitive", name=text)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", text):
        return TypeRef(kind="object", name=text)
    raise ValueError(f"Unsupported TL type: {text}")


def parse_header_ids(header: str) -> dict[str, int]:
    ids: dict[str, int] = {}
    for match in CLASS_ID_RE.finditer(header):
        name, value = match.groups()
        if name in ids:
            raise ValueError(f"Duplicate generated C++ class ID for {name}")
        ids[name] = int(value)
    return ids


def parse_declarations(tl: str, ids: dict[str, int]) -> list[Declaration]:
    declarations: list[Declaration] = []
    is_function = False
    field_docs: dict[str, str] = {}

    for line_number, raw_line in enumerate(tl.splitlines(), start=1):
        line = raw_line.strip()
        if line == "---functions---":
            is_function = True
            field_docs.clear()
            continue
        if line.startswith("//@"):
            for doc_match in DOC_TAG_RE.finditer(line[2:]):
                tag, description = doc_match.groups()
                field_docs[tag] = description
            continue
        if not line or line.startswith("//"):
            continue

        match = DECLARATION_RE.fullmatch(line)
        if match is None:
            if line.startswith(("double ?", "string ?", "vector {")):
                continue
            raise ValueError(f"Unparsed declaration at td_api.tl:{line_number}: {line}")

        name, raw_fields, result = match.groups()
        if name in BUILTIN_DECLARATIONS:
            field_docs.clear()
            continue
        if name not in ids:
            raise ValueError(f"Missing official generated type ID for {name} at line {line_number}")

        fields: list[Field] = []
        for token in raw_fields.split():
            field_match = FIELD_RE.fullmatch(token)
            if field_match is None:
                raise ValueError(f"Invalid field token at td_api.tl:{line_number}: {token}")
            field_name, field_type = field_match.groups()
            try:
                type_ref = parse_type(field_type)
            except ValueError as error:
                raise ValueError(f"td_api.tl:{line_number} {name}.{field_name}: {error}") from error
            fields.append(
                Field(
                    name=field_name,
                    type_ref=type_ref,
                    is_optional=(
                        type_ref.kind == "object"
                        and "null" in field_docs.get(field_name, "").lower()
                    ),
                )
            )

        declarations.append(
            Declaration(
                name=name,
                result=result,
                fields=tuple(fields),
                is_function=is_function,
                type_id=ids[name],
            )
        )
        field_docs.clear()

    return declarations


def walk_types(type_ref: TypeRef) -> Iterable[TypeRef]:
    yield type_ref
    if type_ref.element is not None:
        yield from walk_types(type_ref.element)


def build_document(tl_bytes: bytes, declarations: list[Declaration]) -> dict[str, object]:
    objects = [item for item in declarations if not item.is_function]
    functions = [item for item in declarations if item.is_function]
    known_object_types = {item.result for item in objects} | {item.name for item in objects}
    unknown_object_types: set[str] = set()
    max_vector_depth = 0

    for declaration in declarations:
        for field in declaration.fields:
            depth = 0
            for type_ref in walk_types(field.type_ref):
                if type_ref.kind == "vector":
                    depth += 1
                    max_vector_depth = max(max_vector_depth, depth)
                elif type_ref.kind == "object" and type_ref.name not in known_object_types:
                    unknown_object_types.add(type_ref.name or "")

    if unknown_object_types:
        names = ", ".join(sorted(unknown_object_types))
        raise ValueError(f"Fields refer to unknown TL object roots: {names}")

    unions: dict[str, list[str]] = {}
    for declaration in objects:
        unions.setdefault(declaration.result, []).append(declaration.name)

    return {
        "format_version": 2,
        "tdlib_commit": PINNED_COMMIT,
        "td_api_tl_sha256": hashlib.sha256(tl_bytes).hexdigest(),
        "counts": {
            "declarations": len(declarations),
            "objects": len(objects),
            "functions": len(functions),
            "unions": sum(1 for members in unions.values() if len(members) > 1),
            "result_types": len(unions),
            "fields": sum(len(item.fields) for item in declarations),
            "optional_object_fields": sum(
                field.is_optional
                for item in declarations
                for field in item.fields
            ),
            "max_vector_depth": max_vector_depth,
        },
        "unions": [
            {"name": name, "members": members}
            for name, members in sorted(unions.items())
        ],
        "declarations": [item.json() for item in declarations],
    }


def render(document: dict[str, object]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def field_category(type_ref: TypeRef) -> str:
    if type_ref.kind == "primitive":
        assert type_ref.name is not None
        return {
            "Bool": "bool",
            "bytes": "buffer",
            "double": "double",
            "int32": "int32",
            "int53": "int64",
            "int64": "int64",
            "string": "buffer",
        }[type_ref.name]
    if type_ref.kind == "object":
        return "object"
    assert type_ref.kind == "vector" and type_ref.element is not None
    if type_ref.element.kind == "vector":
        nested = type_ref.element.element
        if nested is None or nested.kind != "object":
            raise ValueError("Only nested object vectors are supported by td_api.tl")
        return "nested_object_vector"
    return f"{field_category(type_ref.element)}_vector"


def render_case_switch(
    declarations: list[Declaration],
    categories: set[str],
    value_expression,
    default_value: str,
    precondition=None,
) -> str:
    lines: list[str] = []
    for declaration in declarations:
        fields = [
            (index, field)
            for index, field in enumerate(declaration.fields)
            if field_category(field.type_ref) in categories
        ]
        if not fields:
            continue
        lines.append(f"    case api::{declaration.name}::ID: {{")
        lines.append(f"      const auto *value = checked<api::{declaration.name}>(object);")
        lines.append(f"      if (value == nullptr) return {default_value};")
        lines.append("      switch (index) {")
        for index, field in fields:
            if precondition is not None:
                for condition_line in precondition(field).splitlines():
                    lines.append(f"        {condition_line}")
            lines.append(f"        case {index}: return {value_expression(field)};")
        lines.append(f"        default: return {default_value};")
        lines.append("      }")
        lines.append("    }")
    return "\n".join(lines)


def render_access_function(
    return_type: str,
    name: str,
    declarations: list[Declaration],
    categories: set[str],
    expression,
    default_value: str,
    extra_parameters: str = "",
    precondition=None,
) -> str:
    cases = render_case_switch(
        declarations,
        categories,
        expression,
        default_value,
        precondition=precondition,
    )
    return (
        f"{return_type} {name}(const api::Object *object, std::int32_t index{extra_parameters}) noexcept {{\n"
        f"  if (object == nullptr) return {default_value};\n"
        "  switch (object->get_id()) {\n"
        f"{cases}\n"
        f"    default: return {default_value};\n"
        "  }\n"
        "}\n"
    )


def render_access_cpp(declarations: list[Declaration]) -> str:
    objects = [item for item in declarations if not item.is_function]

    def member(field: Field) -> str:
        return f"value->{field.name}_"

    functions = [
        render_access_function("bool", "generated_bool_field", objects, {"bool"}, member, "false"),
        render_access_function(
            "std::int32_t", "generated_int32_field", objects, {"int32"}, member, "0"
        ),
        render_access_function(
            "std::int64_t", "generated_int64_field", objects, {"int64"}, member, "0"
        ),
        render_access_function("double", "generated_double_field", objects, {"double"}, member, "0.0"),
        render_access_function(
            "const std::string *",
            "generated_buffer_field",
            objects,
            {"buffer"},
            lambda field: f"&value->{field.name}_",
            "nullptr",
        ),
        render_access_function(
            "const api::Object *",
            "generated_object_field",
            objects,
            {"object"},
            lambda field: f"value->{field.name}_.get()",
            "nullptr",
        ),
        render_access_function(
            "std::size_t",
            "generated_vector_count",
            objects,
            {
                "int32_vector",
                "int64_vector",
                "buffer_vector",
                "object_vector",
                "nested_object_vector",
            },
            lambda field: f"value->{field.name}_.size()",
            "0",
        ),
    ]

    def render_vector_at(
        return_type: str,
        name: str,
        category: str,
        default_value: str,
        item_expression,
    ) -> str:
        lines: list[str] = []
        for declaration in objects:
            fields = [
                (index, field)
                for index, field in enumerate(declaration.fields)
                if field_category(field.type_ref) == category
            ]
            if not fields:
                continue
            lines.append(f"    case api::{declaration.name}::ID: {{")
            lines.append(f"      const auto *value = checked<api::{declaration.name}>(object);")
            lines.append(f"      if (value == nullptr) return {default_value};")
            lines.append("      switch (index) {")
            for index, field in fields:
                vector = f"value->{field.name}_"
                lines.append(f"        case {index}:")
                lines.append(f"          if (element >= {vector}.size()) return {default_value};")
                lines.append(f"          return {item_expression(vector)};")
            lines.append(f"        default: return {default_value};")
            lines.append("      }")
            lines.append("    }")
        return (
            f"{return_type} {name}(const api::Object *object, std::int32_t index, "
            "std::size_t element) noexcept {\n"
            f"  if (object == nullptr) return {default_value};\n"
            "  switch (object->get_id()) {\n"
            + "\n".join(lines)
            + f"\n    default: return {default_value};\n"
            "  }\n"
            "}\n"
        )

    functions.extend(
        [
            render_vector_at(
                "std::int32_t",
                "generated_vector_int32_at",
                "int32_vector",
                "0",
                lambda vector: f"{vector}[element]",
            ),
            render_vector_at(
                "std::int64_t",
                "generated_vector_int64_at",
                "int64_vector",
                "0",
                lambda vector: f"{vector}[element]",
            ),
            render_vector_at(
                "const std::string *",
                "generated_vector_buffer_at",
                "buffer_vector",
                "nullptr",
                lambda vector: f"&{vector}[element]",
            ),
            render_vector_at(
                "const api::Object *",
                "generated_vector_object_at",
                "object_vector",
                "nullptr",
                lambda vector: f"{vector}[element].get()",
            ),
        ]
    )

    nested_count_cases: list[str] = []
    nested_object_cases: list[str] = []
    for declaration in objects:
        fields = [
            (index, field)
            for index, field in enumerate(declaration.fields)
            if field_category(field.type_ref) == "nested_object_vector"
        ]
        if not fields:
            continue
        for target in (nested_count_cases, nested_object_cases):
            target.append(f"    case api::{declaration.name}::ID: {{")
            target.append(f"      const auto *value = checked<api::{declaration.name}>(object);")
            target.append("      if (value == nullptr) return 0;" if target is nested_count_cases else
                          "      if (value == nullptr) return nullptr;")
            target.append("      switch (index) {")
            for index, field in fields:
                vector = f"value->{field.name}_"
                target.append(f"        case {index}:")
                target.append("          if (outer >= " + vector + ".size()) return " +
                              ("0;" if target is nested_count_cases else "nullptr;"))
                if target is nested_count_cases:
                    target.append(f"          return {vector}[outer].size();")
                else:
                    target.append(
                        f"          if (inner >= {vector}[outer].size()) return nullptr;"
                    )
                    target.append(f"          return {vector}[outer][inner].get();")
            target.append("        default: return 0;" if target is nested_count_cases else
                          "        default: return nullptr;")
            target.append("      }")
            target.append("    }")

    functions.append(
        "std::size_t generated_nested_vector_count(const api::Object *object, std::int32_t index, "
        "std::size_t outer) noexcept {\n"
        "  if (object == nullptr) return 0;\n"
        "  switch (object->get_id()) {\n"
        + "\n".join(nested_count_cases)
        + "\n    default: return 0;\n  }\n}\n"
    )
    functions.append(
        "const api::Object *generated_nested_vector_object_at(const api::Object *object, "
        "std::int32_t index, std::size_t outer, std::size_t inner) noexcept {\n"
        "  if (object == nullptr) return nullptr;\n"
        "  switch (object->get_id()) {\n"
        + "\n".join(nested_object_cases)
        + "\n    default: return nullptr;\n  }\n}\n"
    )

    header = (
        "// Generated from Vendor/td/td/generate/scheme/td_api.tl. Do not edit.\n"
        f"// TDLib commit: {PINNED_COMMIT}\n\n"
    )
    return header + "\n".join(functions)


SWIFT_KEYWORDS = {
    "as", "associatedtype", "break", "case", "catch", "class", "continue", "default",
    "defer", "deinit", "do", "else", "enum", "extension", "fallthrough", "false", "fileprivate",
    "for", "func", "guard", "if", "import", "in", "init", "inout", "internal", "is", "let",
    "nil", "operator", "private", "protocol", "public", "repeat", "rethrows", "return", "self",
    "Self", "static", "struct", "subscript", "super", "switch", "throw", "throws", "true", "try",
    "typealias", "var", "where", "while",
}


def upper_first(value: str) -> str:
    return value[:1].upper() + value[1:]


def lower_first(value: str) -> str:
    return value[:1].lower() + value[1:]


def lower_camel(value: str) -> str:
    parts = value.split("_")
    result = parts[0] + "".join(upper_first(part) for part in parts[1:])
    return f"`{result}`" if result in SWIFT_KEYWORDS else result


def concrete_swift_name(name: str) -> str:
    return "TDNative" + upper_first(name)


def render_swift_views(declarations: list[Declaration]) -> str:
    objects = [item for item in declarations if not item.is_function]
    by_name = {item.name: item for item in objects}
    by_result: dict[str, list[Declaration]] = {}
    for item in objects:
        by_result.setdefault(item.result, []).append(item)

    def view_name(tl_name: str) -> str:
        if tl_name in by_name:
            return concrete_swift_name(tl_name)
        members = by_result[tl_name]
        if len(members) == 1:
            return concrete_swift_name(members[0].name)
        return "TDNative" + tl_name

    def optional_decode(tl_name: str, native_expression: str) -> str:
        return f"{view_name(tl_name)}(native: {native_expression})"

    def scalar_property(field: Field, index: int) -> tuple[str, str]:
        assert field.type_ref.name is not None
        name = field.type_ref.name
        if name == "Bool":
            return "Bool", f"native.value.bool_field({index})"
        if name == "int32":
            return "Int", f"Int(native.value.int32_field({index}))"
        if name in {"int53", "int64"}:
            return "Int64", f"native.value.int64_field({index})"
        if name == "double":
            return "Double", f"native.value.double_field({index})"
        if name == "string":
            return "String", f"swiftString(native.value.buffer_field({index}))"
        if name == "bytes":
            return "Data", f"swiftData(native.value.buffer_field({index}))"
        raise ValueError(f"Unsupported primitive field {name}")

    def property_lines(field: Field, index: int) -> list[str]:
        property_name = lower_camel(field.name)
        type_ref = field.type_ref
        if type_ref.kind == "primitive":
            swift_type, expression = scalar_property(field, index)
            return [f"    public var {property_name}: {swift_type} {{ {expression} }}"]
        if type_ref.kind == "object":
            assert type_ref.name is not None
            swift_type = view_name(type_ref.name)
            result = [
                f"    public var {property_name}: {swift_type}{'?' if field.is_optional else ''} {{",
                f"        let object = NativeOwnedObject(value: native.value.object_field({index}))",
            ]
            if field.is_optional:
                result.append(f"        return {optional_decode(type_ref.name, 'object')}")
            else:
                result.extend(
                    [
                        f"        guard let value = {optional_decode(type_ref.name, 'object')} else {{",
                        f"            preconditionFailure(\"Required field {property_name} is null\")",
                        "        }",
                        "        return value",
                    ]
                )
            result.append("    }")
            return result

        assert type_ref.kind == "vector" and type_ref.element is not None
        element = type_ref.element
        if element.kind == "primitive":
            assert element.name is not None
            if element.name == "int32":
                swift_type, accessor = "Int", "vector_int32_at"
                conversion = lambda call: f"Int({call})"
            elif element.name in {"int53", "int64"}:
                swift_type, accessor = "Int64", "vector_int64_at"
                conversion = lambda call: call
            elif element.name == "string":
                swift_type, accessor = "String", "vector_buffer_at"
                conversion = lambda call: f"swiftString({call})"
            elif element.name == "bytes":
                swift_type, accessor = "Data", "vector_buffer_at"
                conversion = lambda call: f"swiftData({call})"
            else:
                raise ValueError(f"Unsupported vector primitive {element.name}")
            call = f"native.value.{accessor}({index}, element)"
            return [
                f"    public var {property_name}: [{swift_type}] {{",
                f"        let count = native.value.vector_count({index})",
                f"        return (0..<count).map {{ element in {conversion(call)} }}",
                "    }",
            ]
        if element.kind == "object":
            assert element.name is not None
            swift_type = view_name(element.name)
            return [
                f"    public var {property_name}: [{swift_type}] {{",
                f"        let count = native.value.vector_count({index})",
                "        return (0..<count).compactMap { element in",
                "            let object = NativeOwnedObject(",
                f"                value: native.value.vector_object_at({index}, element)",
                "            )",
                f"            return {optional_decode(element.name, 'object')}",
                "        }",
                "    }",
            ]
        assert element.kind == "vector" and element.element is not None
        nested = element.element
        if nested.kind != "object" or nested.name is None:
            raise ValueError("Only nested object vectors are supported")
        swift_type = view_name(nested.name)
        return [
            f"    public var {property_name}: [[{swift_type}]] {{",
            f"        let outerCount = native.value.vector_count({index})",
            "        return (0..<outerCount).map { outer in",
            f"            let innerCount = native.value.nested_vector_count({index}, outer)",
            "            return (0..<innerCount).compactMap { inner in",
            "                let object = NativeOwnedObject(",
            f"                    value: native.value.nested_vector_object_at({index}, outer, inner)",
            "                )",
            f"                return {optional_decode(nested.name, 'object')}",
            "            }",
            "        }",
            "    }",
        ]

    def swift_input_type(type_ref: TypeRef, is_optional: bool = False) -> str:
        if type_ref.kind == "primitive":
            assert type_ref.name is not None
            return {
                "Bool": "Bool",
                "bytes": "Data",
                "double": "Double",
                "int32": "Int",
                "int53": "Int64",
                "int64": "Int64",
                "string": "String",
            }[type_ref.name]
        if type_ref.kind == "object":
            assert type_ref.name is not None
            return view_name(type_ref.name) + ("?" if is_optional else "")
        assert type_ref.kind == "vector" and type_ref.element is not None
        return f"[{swift_input_type(type_ref.element).removesuffix('?')}]"

    def argument_lines(
        type_ref: TypeRef,
        value_name: str,
        unique_index: int,
        is_optional: bool = False,
    ) -> list[str]:
        category = field_category(type_ref)
        if category == "bool":
            return [f"arguments.append_bool({value_name})"]
        if category == "int32":
            return [f"arguments.append_int32(nativeInt32({value_name}))"]
        if category == "int64":
            return [f"arguments.append_int64({value_name})"]
        if category == "double":
            return [f"arguments.append_double({value_name})"]
        if category == "buffer":
            return [f"arguments.append_buffer(nativeBuffer({value_name}))"]
        if category == "object":
            if is_optional:
                return [
                    f"arguments.append_object({value_name}?.native.value ?? tdlibkit.NativeObject())"
                ]
            return [f"arguments.append_object({value_name}.native.value)"]
        if category == "int32_vector":
            array_name = f"nativeValues{unique_index}"
            return [
                f"let {array_name} = {value_name}.map(nativeInt32)",
                f"{array_name}.withUnsafeBufferPointer {{ buffer in",
                "    arguments.append_int32_vector(buffer.baseAddress, buffer.count)",
                "}",
            ]
        if category == "int64_vector":
            return [
                f"{value_name}.withUnsafeBufferPointer {{ buffer in",
                "    arguments.append_int64_vector(buffer.baseAddress, buffer.count)",
                "}",
            ]
        if category == "buffer_vector":
            array_name = f"nativeValues{unique_index}"
            return [
                f"var {array_name} = tdlibkit.NativeBufferArray()",
                f"for value in {value_name} {{ {array_name}.append(nativeBuffer(value)) }}",
                f"arguments.append_buffer_vector({array_name})",
            ]
        if category == "object_vector":
            array_name = f"nativeValues{unique_index}"
            return [
                f"var {array_name} = tdlibkit.NativeObjectArray()",
                f"for value in {value_name} {{ {array_name}.append(value.native.value) }}",
                f"arguments.append_object_vector({array_name})",
            ]
        if category == "nested_object_vector":
            rows_name = f"nativeRows{unique_index}"
            row_name = f"nativeRow{unique_index}"
            return [
                f"var {rows_name} = tdlibkit.NativeObjectArrayArray()",
                f"for row in {value_name} {{",
                f"    var {row_name} = tdlibkit.NativeObjectArray()",
                f"    for value in row {{ {row_name}.append(value.native.value) }}",
                f"    {rows_name}.append({row_name})",
                "}",
                f"arguments.append_nested_object_vector({rows_name})",
            ]
        raise ValueError(f"Unsupported argument type: {type_ref}")

    def parameters(fields: tuple[Field, ...]) -> str:
        return ", ".join(
            f"{lower_camel(field.name)}: {swift_input_type(field.type_ref, field.is_optional)}"
            for field in fields
        )

    def parameter_arguments(fields: tuple[Field, ...]) -> str:
        result: list[str] = []
        for field in fields:
            value_name = lower_camel(field.name)
            result.append(f"{value_name.strip('`')}: {value_name}")
        return ", ".join(result)

    def append_arguments(fields: tuple[Field, ...], indent: str) -> list[str]:
        result: list[str] = []
        for index, field in enumerate(fields):
            for line in argument_lines(
                field.type_ref,
                lower_camel(field.name),
                index,
                field.is_optional,
            ):
                result.append(indent + line)
        return result

    lines = [
        "// Generated from Vendor/td/td/generate/scheme/td_api.tl. Do not edit.",
        f"// TDLib commit: {PINNED_COMMIT}",
        "",
        "import Foundation",
        "import TDLibCxxBridge",
        "",
        "@inline(__always)",
        "private func nativeInt32(_ value: Int) -> Int32 {",
        "    guard let result = Int32(exactly: value) else {",
        "        preconditionFailure(\"TDLib int32 value is out of range: \\(value)\")",
        "    }",
        "    return result",
        "}",
        "",
        "public protocol TDNativeObjectView: Sendable {",
        "    static var typeID: Int32 { get }",
        "    var typeID: Int32 { get }",
        "}",
        "",
    ]

    for declaration in objects:
        swift_name = concrete_swift_name(declaration.name)
        lines.extend(
            [
                f"public struct {swift_name}: TDNativeObjectView, TDNativeObjectBacked, @unchecked Sendable {{",
                f"    public static let typeID: Int32 = {declaration.type_id}",
                "    let native: NativeOwnedObject",
                "",
                "    init?(native: NativeOwnedObject) {",
                "        guard native.value.is_valid(), native.value.type_id() == Self.typeID else {",
                "            return nil",
                "        }",
                "        self.native = native",
                "    }",
                "",
                "    public init?(_ object: TDUnknownObject) {",
                "        self.init(native: object.native)",
                "    }",
                "",
                "    public var typeID: Int32 { Self.typeID }",
            ]
        )
        signature = parameters(declaration.fields)
        lines.extend(
            [
                "",
                f"    public init({signature}) {{",
                "        " + ("var" if declaration.fields else "let") +
                " arguments = tdlibkit.NativeArguments()",
            ]
        )
        lines.extend(append_arguments(declaration.fields, "        "))
        lines.extend(
            [
                "        let object = NativeOwnedObject(",
                "            value: tdlibkit.NativeSchemaFactory.make_object(Self.typeID, arguments)",
                "        )",
                "        guard let value = Self(native: object) else {",
                f"            preconditionFailure(\"Unable to construct {swift_name}\")",
                "        }",
                "        self = value",
                "    }",
                "",
                f"    public static func make({signature}) -> Self? {{",
                f"        Self({parameter_arguments(declaration.fields)})",
                "    }",
            ]
        )
        for index, field in enumerate(declaration.fields):
            lines.append("")
            lines.extend(property_lines(field, index))
        lines.extend(["}", ""])

    for result_name, members in sorted(by_result.items()):
        if len(members) <= 1:
            continue
        swift_name = "TDNative" + result_name
        lines.append(
            f"public enum {swift_name}: TDNativeObjectView, TDNativeObjectBacked, Sendable {{"
        )
        for member in members:
            case_name = lower_first(upper_first(member.name))
            if case_name in SWIFT_KEYWORDS:
                case_name = f"`{case_name}`"
            concrete = concrete_swift_name(member.name)
            if member.fields:
                lines.append(
                    f"    case {case_name}({concrete_swift_name(member.name)})"
                )
            else:
                lines.append(f"    case {case_name}")
        lines.extend(
            [
                "",
                "    init?(native: NativeOwnedObject) {",
                "        switch native.value.type_id() {",
            ]
        )
        for member in members:
            case_name = lower_first(upper_first(member.name))
            if case_name in SWIFT_KEYWORDS:
                case_name = f"`{case_name}`"
            concrete = concrete_swift_name(member.name)
            lines.append(f"        case {concrete}.typeID:")
            if member.fields:
                lines.extend(
                    [
                        f"            guard let value = {concrete}(native: native) else {{ return nil }}",
                        f"            self = .{case_name}(value)",
                    ]
                )
            else:
                lines.append(f"            self = .{case_name}")
        lines.extend(
            [
                "        default:",
                "            return nil",
                "        }",
                "    }",
                "",
                "    public init?(_ object: TDUnknownObject) {",
                "        self.init(native: object.native)",
                "    }",
                "",
                "    public static var typeID: Int32 { 0 }",
                "",
                "    var native: NativeOwnedObject {",
                "        switch self {",
            ]
        )
        for member in members:
            case_name = lower_first(upper_first(member.name))
            if case_name in SWIFT_KEYWORDS:
                case_name = f"`{case_name}`"
            concrete = concrete_swift_name(member.name)
            if member.fields:
                lines.append(f"        case .{case_name}(let value): return value.native")
            else:
                lines.append(f"        case .{case_name}: return {concrete}().native")
        lines.extend(
            [
                "        }",
                "    }",
                "",
                "    public var typeID: Int32 {",
                "        switch self {",
            ]
        )
        for member in members:
            case_name = lower_first(upper_first(member.name))
            if case_name in SWIFT_KEYWORDS:
                case_name = f"`{case_name}`"
            if member.fields:
                lines.append(f"        case .{case_name}(let value): return value.typeID")
            else:
                lines.append(f"        case .{case_name}: return {concrete}.typeID")
        lines.extend(["        }", "    }", "}", ""])

    lines.append("public enum TDNativeRequests {")
    for declaration in (item for item in declarations if item.is_function):
        method_name = lower_camel(declaration.name)
        result_type = view_name(declaration.result)
        signature = parameters(declaration.fields)
        lines.extend(
            [
                f"    public static func {method_name}({signature}) -> TDRequest<{result_type}> {{",
                "        TDRequest(",
                "            make: {",
                "                " + ("var" if declaration.fields else "let") +
                " arguments = tdlibkit.NativeArguments()",
            ]
        )
        lines.extend(append_arguments(declaration.fields, "                "))
        lines.extend(
            [
                "                return tdlibkit.NativeSchemaFactory.make_function(",
                f"                    {declaration.type_id},",
                "                    arguments",
                "                )",
                "            },",
                "            decode: { object in",
                f"                guard let value = {result_type}(native: object) else {{",
                "                    throw TDLibRuntimeError.unexpectedType(",
                f"                        expected: \"{declaration.result}\",",
                "                        actualTypeID: object.value.type_id()",
                "                    )",
                "                }",
                "                return value",
                "            }",
                "        )",
                "    }",
                "",
            ]
        )
    lines.append("}")

    return "\n".join(lines) + "\n"


def render_factory_cpp(declarations: list[Declaration]) -> str:
    objects = [item for item in declarations if not item.is_function]
    by_name = {item.name: item for item in objects}
    by_result: dict[str, list[Declaration]] = {}
    for item in objects:
        by_result.setdefault(item.result, []).append(item)

    def allowed_ids(type_name: str) -> list[str]:
        members = [by_name[type_name]] if type_name in by_name else by_result[type_name]
        return [f"api::{member.name}::ID" for member in members]

    def validate(field: Field, index: int) -> str | None:
        category = field_category(field.type_ref)
        if category == "object":
            assert field.type_ref.name is not None
            ids = ", ".join(allowed_ids(field.type_ref.name))
            nullable = "true" if field.is_optional else "false"
            return (
                f"NativeArgumentAccess::object_matches(arguments, {index}, "
                f"{{{ids}}}, {nullable})"
            )
        if category == "object_vector":
            assert field.type_ref.element is not None and field.type_ref.element.name is not None
            ids = ", ".join(allowed_ids(field.type_ref.element.name))
            return f"NativeArgumentAccess::object_vector_matches(arguments, {index}, {{{ids}}})"
        if category == "nested_object_vector":
            assert field.type_ref.element is not None
            nested = field.type_ref.element.element
            assert nested is not None and nested.name is not None
            ids = ", ".join(allowed_ids(nested.name))
            return (
                f"NativeArgumentAccess::nested_object_vector_matches(arguments, {index}, "
                f"{{{ids}}})"
            )
        return None

    def value(field: Field, index: int) -> str:
        type_ref = field.type_ref
        category = field_category(type_ref)
        if category == "bool":
            return f"NativeArgumentAccess::bool_at(arguments, {index})"
        if category == "int32":
            return f"NativeArgumentAccess::int32_at(arguments, {index})"
        if category == "int64":
            return f"NativeArgumentAccess::int64_at(arguments, {index})"
        if category == "double":
            return f"NativeArgumentAccess::double_at(arguments, {index})"
        if category == "buffer":
            return f"NativeArgumentAccess::buffer_at(arguments, {index})"
        if category == "object":
            assert type_ref.name is not None
            return f"NativeArgumentAccess::object_at<api::{type_ref.name}>(arguments, {index}, valid)"
        if category == "int32_vector":
            return f"NativeArgumentAccess::int32_vector_at(arguments, {index})"
        if category == "int64_vector":
            return f"NativeArgumentAccess::int64_vector_at(arguments, {index})"
        if category == "buffer_vector":
            return f"NativeArgumentAccess::buffer_vector_at(arguments, {index})"
        if category == "object_vector":
            assert type_ref.element is not None and type_ref.element.name is not None
            return (
                f"NativeArgumentAccess::object_vector_at<api::{type_ref.element.name}>"
                f"(arguments, {index}, valid)"
            )
        if category == "nested_object_vector":
            assert type_ref.element is not None and type_ref.element.element is not None
            nested = type_ref.element.element
            assert nested.name is not None
            return (
                f"NativeArgumentAccess::nested_object_vector_at<api::{nested.name}>"
                f"(arguments, {index}, valid)"
            )
        raise ValueError(f"Unsupported factory field: {field}")

    def factory(
        name: str,
        items: list[Declaration],
        base_type: str,
    ) -> str:
        lines = [
            f"api::object_ptr<api::{base_type}> {name}(",
            "    std::int32_t type_id, NativeArgumentsStorage &arguments) noexcept {",
            "  switch (type_id) {",
        ]
        for declaration in items:
            lines.append(f"    case api::{declaration.name}::ID: {{")
            lines.append(
                f"      if (arguments.values_.size() != {len(declaration.fields)}) return nullptr;"
            )
            for index, field in enumerate(declaration.fields):
                condition = validate(field, index)
                if condition is not None:
                    lines.append(f"      if (!{condition}) return nullptr;")
            has_objects = any(
                field_category(field.type_ref) in {"object", "object_vector", "nested_object_vector"}
                for field in declaration.fields
            )
            if has_objects:
                lines.append("      bool valid = true;")
            lines.append(f"      auto result = api::make_object<api::{declaration.name}>();")
            for index, field in enumerate(declaration.fields):
                lines.append(f"      result->{field.name}_ = {value(field, index)};")
            if has_objects:
                lines.append("      if (!valid) return nullptr;")
            lines.append(
                f"      return api::object_ptr<api::{base_type}>(std::move(result));"
            )
            lines.append("    }")
        lines.extend(["    default: return nullptr;", "  }", "}", ""])
        return "\n".join(lines)

    header = (
        "// Generated from Vendor/td/td/generate/scheme/td_api.tl. Do not edit.\n"
        f"// TDLib commit: {PINNED_COMMIT}\n\n"
    )
    clone = [
        "api::object_ptr<api::Object> generated_clone_schema_object(",
        "    const api::Object *object, bool &valid) noexcept {",
        "  if (object == nullptr) return nullptr;",
        "  switch (object->get_id()) {",
    ]
    for declaration in objects:
        clone.append(f"    case api::{declaration.name}::ID: {{")
        if declaration.fields:
            clone.append(f"      const auto *value = static_cast<const api::{declaration.name} *>(object);")
        clone.append(f"      auto result = api::make_object<api::{declaration.name}>();")
        for field in declaration.fields:
            expression = f"value->{field.name}_"
            if field_category(field.type_ref) in {"object", "object_vector", "nested_object_vector"}:
                expression = f"clone_schema_value({expression}, valid)"
            clone.append(f"      result->{field.name}_ = {expression};")
        clone.append("      return api::object_ptr<api::Object>(std::move(result));")
        clone.append("    }")
    clone.extend(["    default:", "      valid = false;", "      return nullptr;", "  }", "}", ""])
    return header + "\n".join(clone) + factory("generated_make_schema_object", objects, "Object") + factory(
        "generated_make_schema_function",
        [item for item in declarations if item.is_function],
        "Function",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--access-output", type=Path, default=DEFAULT_ACCESS_OUTPUT)
    parser.add_argument("--swift-output", type=Path, default=DEFAULT_SWIFT_OUTPUT)
    parser.add_argument("--factory-output", type=Path, default=DEFAULT_FACTORY_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    verify_source()

    if not TL_PATH.is_file():
        parser.error(f"Missing pinned schema: {TL_PATH}")
    if not HEADER_PATH.is_file():
        parser.error(
            f"Missing official generated header: {HEADER_PATH}. "
            "Run ./scripts/tdlib-native.sh generate first."
        )

    tl_bytes = TL_PATH.read_bytes()
    tl = tl_bytes.decode("utf-8")
    header = HEADER_PATH.read_text(encoding="utf-8")
    declarations = parse_declarations(tl, parse_header_ids(header))
    document = build_document(tl_bytes, declarations)
    generated = render(document)
    generated_access = render_access_cpp(declarations)
    generated_swift = render_swift_views(declarations)
    generated_factory = render_factory_cpp(declarations)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    access_output = (
        args.access_output if args.access_output.is_absolute() else ROOT / args.access_output
    )
    swift_output = args.swift_output if args.swift_output.is_absolute() else ROOT / args.swift_output
    factory_output = (
        args.factory_output if args.factory_output.is_absolute() else ROOT / args.factory_output
    )

    if args.check:
        stale = []
        if not output.is_file() or output.read_text(encoding="utf-8") != generated:
            stale.append(output)
        if (
            not access_output.is_file()
            or access_output.read_text(encoding="utf-8") != generated_access
        ):
            stale.append(access_output)
        if (
            not swift_output.is_file()
            or swift_output.read_text(encoding="utf-8") != generated_swift
        ):
            stale.append(swift_output)
        if (
            not factory_output.is_file()
            or factory_output.read_text(encoding="utf-8") != generated_factory
        ):
            stale.append(factory_output)
        if stale:
            print("Generated schema is stale: " + ", ".join(map(str, stale)), file=sys.stderr)
            return 1
        print(
            f"Generated schema is clean: {output}, {access_output}, "
            f"{swift_output}, {factory_output}"
        )
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generated, encoding="utf-8")
    access_output.parent.mkdir(parents=True, exist_ok=True)
    access_output.write_text(generated_access, encoding="utf-8")
    swift_output.parent.mkdir(parents=True, exist_ok=True)
    swift_output.write_text(generated_swift, encoding="utf-8")
    factory_output.parent.mkdir(parents=True, exist_ok=True)
    factory_output.write_text(generated_factory, encoding="utf-8")
    print(json.dumps(document["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        sys.exit(f"Schema generation stopped: {error}")
