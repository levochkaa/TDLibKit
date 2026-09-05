#include "TDLibCxxBridge/Bridge.hpp"

// Keep implementation symbols private without SwiftPM unsafeFlags, which would
// prevent consumers from selecting this package by a semantic version.
#pragma GCC visibility push(hidden)

#include "td/telegram/Client.h"
#include "td/telegram/td_api.h"
#include "td/telegram/td_api.hpp"

#include <algorithm>
#include <cstring>
#include <initializer_list>
#include <mutex>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace tdlibkit {
namespace api = td::td_api;

struct NativeBufferStorage {
  explicit NativeBufferStorage(std::string bytes) noexcept : bytes_(std::move(bytes)) {
  }
  std::string bytes_;
};

struct NativeFunctionStorage {
  explicit NativeFunctionStorage(api::object_ptr<api::Function> function) noexcept
      : function_(std::move(function)) {
  }

  api::object_ptr<api::Function> take() noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    return std::move(function_);
  }

  mutable std::mutex mutex_;
  api::object_ptr<api::Function> function_;
};

struct NativeObjectRoot {
  explicit NativeObjectRoot(api::object_ptr<api::Object> object) noexcept : object_(std::move(object)) {
  }
  const api::object_ptr<api::Object> object_;
};

struct NativeObjectStorage {
  NativeObjectStorage(std::shared_ptr<const NativeObjectRoot> root, const api::Object *object) noexcept
      : root_(std::move(root)), object_(object) {
  }
  const std::shared_ptr<const NativeObjectRoot> root_;
  const api::Object *const object_;
};

struct NativeManagerStorage {
  td::ClientManager manager_;
};

struct NativeBufferArrayStorage {
  std::vector<std::string> values_;
};

struct NativeObjectArrayStorage {
  std::vector<NativeObject> values_;
};

struct NativeObjectArrayArrayStorage {
  std::vector<std::vector<NativeObject>> values_;
};

using NativeInt32Vector = std::vector<std::int32_t>;
using NativeInt64Vector = std::vector<std::int64_t>;
using NativeBufferVector = std::vector<std::string>;
using NativeObjectVector = std::vector<NativeObject>;
using NativeNestedObjectVector = std::vector<std::vector<NativeObject>>;
using NativeArgument = std::variant<
    bool,
    std::int32_t,
    std::int64_t,
    double,
    std::string,
    NativeObject,
    NativeInt32Vector,
    NativeInt64Vector,
    NativeBufferVector,
    NativeObjectVector,
    NativeNestedObjectVector>;

struct NativeArgumentsStorage {
  std::vector<NativeArgument> values_;
};

namespace {

api::object_ptr<api::Object> generated_clone_schema_object(
    const api::Object *object, bool &valid) noexcept;

template <class T>
api::object_ptr<T> clone_schema_value(const api::object_ptr<T> &object, bool &valid) noexcept {
  return api::move_object_as<T>(generated_clone_schema_object(object.get(), valid));
}

template <class T>
std::vector<T> clone_schema_value(const std::vector<T> &values, bool &valid) noexcept {
  std::vector<T> result;
  result.reserve(values.size());
  for (const auto &value : values) {
    result.push_back(clone_schema_value(value, valid));
  }
  return result;
}

}  // namespace

struct NativeArgumentAccess {
  template <class T>
  static T *at(NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    if (index >= arguments.values_.size()) {
      return nullptr;
    }
    return std::get_if<T>(&arguments.values_[index]);
  }

  static bool bool_at(NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    const auto *value = at<bool>(arguments, index);
    return value == nullptr ? false : *value;
  }

  static std::int32_t int32_at(NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    const auto *value = at<std::int32_t>(arguments, index);
    return value == nullptr ? 0 : *value;
  }

  static std::int64_t int64_at(NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    const auto *value = at<std::int64_t>(arguments, index);
    return value == nullptr ? 0 : *value;
  }

  static double double_at(NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    const auto *value = at<double>(arguments, index);
    return value == nullptr ? 0.0 : *value;
  }

  static std::string buffer_at(NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    auto *value = at<std::string>(arguments, index);
    return value == nullptr ? std::string() : std::move(*value);
  }

  template <class T>
  static api::object_ptr<T> clone_native_object(const NativeObject &object, bool &valid) noexcept {
    // A default handle is an explicit null. Any other invalid handle is an error.
    if (object.storage_ == nullptr) {
      return nullptr;
    }
    if (!object.is_valid()) {
      valid = false;
      return nullptr;
    }
    // Clone the selected subtree, including when this handle is a child view.
    return api::move_object_as<T>(generated_clone_schema_object(object.storage_->object_, valid));
  }

  static bool type_is_allowed(
      std::int32_t type_id, std::initializer_list<std::int32_t> allowed) noexcept {
    return std::find(allowed.begin(), allowed.end(), type_id) != allowed.end();
  }

  static bool object_matches(
      NativeArgumentsStorage &arguments,
      std::size_t index,
      std::initializer_list<std::int32_t> allowed,
      bool nullable) noexcept {
    auto *value = at<NativeObject>(arguments, index);
    return value != nullptr &&
        ((value->storage_ == nullptr && nullable) ||
         (value->is_valid() && type_is_allowed(value->type_id(), allowed)));
  }

  static bool object_vector_matches(
      NativeArgumentsStorage &arguments,
      std::size_t index,
      std::initializer_list<std::int32_t> allowed) noexcept {
    auto *values = at<NativeObjectVector>(arguments, index);
    if (values == nullptr) {
      return false;
    }
    for (const auto &value : *values) {
      if (!value.is_valid() || !type_is_allowed(value.type_id(), allowed)) {
        return false;
      }
    }
    return true;
  }

  static bool nested_object_vector_matches(
      NativeArgumentsStorage &arguments,
      std::size_t index,
      std::initializer_list<std::int32_t> allowed) noexcept {
    auto *rows = at<NativeNestedObjectVector>(arguments, index);
    if (rows == nullptr) {
      return false;
    }
    for (const auto &row : *rows) {
      for (const auto &value : row) {
        if (!value.is_valid() || !type_is_allowed(value.type_id(), allowed)) {
          return false;
        }
      }
    }
    return true;
  }

  template <class T>
  static api::object_ptr<T> object_at(
      NativeArgumentsStorage &arguments, std::size_t index, bool &valid) noexcept {
    auto *value = at<NativeObject>(arguments, index);
    return value == nullptr ? nullptr : clone_native_object<T>(*value, valid);
  }

  static NativeInt32Vector int32_vector_at(
      NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    auto *value = at<NativeInt32Vector>(arguments, index);
    return value == nullptr ? NativeInt32Vector() : std::move(*value);
  }

  static NativeInt64Vector int64_vector_at(
      NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    auto *value = at<NativeInt64Vector>(arguments, index);
    return value == nullptr ? NativeInt64Vector() : std::move(*value);
  }

  static NativeBufferVector buffer_vector_at(
      NativeArgumentsStorage &arguments, std::size_t index) noexcept {
    auto *value = at<NativeBufferVector>(arguments, index);
    return value == nullptr ? NativeBufferVector() : std::move(*value);
  }

  template <class T>
  static std::vector<api::object_ptr<T>> object_vector_at(
      NativeArgumentsStorage &arguments, std::size_t index, bool &valid) noexcept {
    std::vector<api::object_ptr<T>> result;
    auto *values = at<NativeObjectVector>(arguments, index);
    if (values == nullptr) {
      return result;
    }
    result.reserve(values->size());
    for (auto &value : *values) {
      result.push_back(clone_native_object<T>(value, valid));
    }
    return result;
  }

  template <class T>
  static std::vector<std::vector<api::object_ptr<T>>> nested_object_vector_at(
      NativeArgumentsStorage &arguments, std::size_t index, bool &valid) noexcept {
    std::vector<std::vector<api::object_ptr<T>>> result;
    auto *rows = at<NativeNestedObjectVector>(arguments, index);
    if (rows == nullptr) {
      return result;
    }
    result.reserve(rows->size());
    for (auto &row : *rows) {
      std::vector<api::object_ptr<T>> native_row;
      native_row.reserve(row.size());
      for (auto &value : row) {
        native_row.push_back(clone_native_object<T>(value, valid));
      }
      result.push_back(std::move(native_row));
    }
    return result;
  }
};

struct NativeObjectFactoryAccess {
  static NativeObject make(api::object_ptr<api::Object> object) noexcept {
    if (object == nullptr) {
      return NativeObject();
    }
    auto root = std::make_shared<NativeObjectRoot>(std::move(object));
    return NativeObject(std::make_shared<NativeObjectStorage>(root, root->object_.get()));
  }
};

namespace {

std::string buffer_string(const NativeBuffer &buffer) noexcept {
  const auto size = buffer.size();
  std::string result(size, '\0');
  if (size != 0) {
    buffer.copy_to(reinterpret_cast<std::uint8_t *>(result.data()), size);
  }
  return result;
}

template <class T>
const T *checked(const api::Object *object) noexcept {
  if (object == nullptr || object->get_id() != T::ID) {
    return nullptr;
  }
  return static_cast<const T *>(object);
}

const api::Object *child_pointer(const api::Object *object, NativeChildField field) noexcept {
  switch (field) {
    case NativeChildField::update_authorization_state: {
      const auto *value = checked<api::updateAuthorizationState>(object);
      return value == nullptr ? nullptr : value->authorization_state_.get();
    }
    case NativeChildField::update_new_message: {
      const auto *value = checked<api::updateNewMessage>(object);
      return value == nullptr ? nullptr : value->message_.get();
    }
    case NativeChildField::message_content: {
      const auto *value = checked<api::message>(object);
      return value == nullptr ? nullptr : value->content_.get();
    }
    case NativeChildField::message_text_text: {
      const auto *value = checked<api::messageText>(object);
      return value == nullptr ? nullptr : value->text_.get();
    }
  }
  return nullptr;
}

#include "Generated/SchemaAccess.inc"
#include "Generated/SchemaFactory.inc"

}  // namespace

NativeBuffer::NativeBuffer() noexcept = default;
NativeBuffer::NativeBuffer(const NativeBuffer &) noexcept = default;
NativeBuffer::NativeBuffer(NativeBuffer &&) noexcept = default;
NativeBuffer &NativeBuffer::operator=(const NativeBuffer &) noexcept = default;
NativeBuffer &NativeBuffer::operator=(NativeBuffer &&) noexcept = default;
NativeBuffer::~NativeBuffer() noexcept = default;

NativeBuffer::NativeBuffer(std::shared_ptr<NativeBufferStorage> storage) noexcept : storage_(std::move(storage)) {
}

NativeBuffer NativeBuffer::copy(const std::uint8_t *bytes, std::size_t count) noexcept {
  if (bytes == nullptr || count == 0) {
    return NativeBuffer(std::make_shared<NativeBufferStorage>(std::string()));
  }
  return NativeBuffer(std::make_shared<NativeBufferStorage>(
      std::string(reinterpret_cast<const char *>(bytes), count)));
}

std::size_t NativeBuffer::size() const noexcept {
  return storage_ == nullptr ? 0 : storage_->bytes_.size();
}

std::size_t NativeBuffer::copy_to(std::uint8_t *destination, std::size_t capacity) const noexcept {
  const auto count = size();
  if (destination != nullptr && capacity != 0 && storage_ != nullptr) {
    std::memcpy(destination, storage_->bytes_.data(), std::min(count, capacity));
  }
  return count;
}

NativeObject::NativeObject() noexcept = default;
NativeObject::NativeObject(const NativeObject &) noexcept = default;
NativeObject::NativeObject(NativeObject &&) noexcept = default;
NativeObject &NativeObject::operator=(const NativeObject &) noexcept = default;
NativeObject &NativeObject::operator=(NativeObject &&) noexcept = default;
NativeObject::~NativeObject() noexcept = default;

NativeObject::NativeObject(std::shared_ptr<NativeObjectStorage> storage) noexcept : storage_(std::move(storage)) {
}

bool NativeObject::is_valid() const noexcept {
  return storage_ != nullptr && storage_->root_ != nullptr &&
      storage_->root_->object_ != nullptr && storage_->object_ != nullptr;
}

std::int32_t NativeObject::type_id() const noexcept {
  return is_valid() ? storage_->object_->get_id() : 0;
}

NativeObjectKind NativeObject::kind() const noexcept {
  switch (type_id()) {
    case api::error::ID: return NativeObjectKind::error;
    case api::ok::ID: return NativeObjectKind::ok;
    case api::optionValueString::ID: return NativeObjectKind::option_value_string;
    case api::updateAuthorizationState::ID: return NativeObjectKind::update_authorization_state;
    case api::updateNewMessage::ID: return NativeObjectKind::update_new_message;
    case api::authorizationStateWaitTdlibParameters::ID:
      return NativeObjectKind::authorization_state_wait_tdlib_parameters;
    case api::authorizationStateWaitPhoneNumber::ID:
      return NativeObjectKind::authorization_state_wait_phone_number;
    case api::authorizationStateReady::ID: return NativeObjectKind::authorization_state_ready;
    case api::authorizationStateLoggingOut::ID: return NativeObjectKind::authorization_state_logging_out;
    case api::authorizationStateClosing::ID: return NativeObjectKind::authorization_state_closing;
    case api::authorizationStateClosed::ID: return NativeObjectKind::authorization_state_closed;
    case api::messages::ID: return NativeObjectKind::messages;
    case api::message::ID: return NativeObjectKind::message;
    case api::messageText::ID: return NativeObjectKind::message_text;
    case api::formattedText::ID: return NativeObjectKind::formatted_text;
    default: return NativeObjectKind::unknown;
  }
}

NativeObject NativeObject::child(NativeChildField field) const noexcept {
  if (!is_valid()) {
    return NativeObject();
  }
  const auto *pointer = child_pointer(storage_->object_, field);
  if (pointer == nullptr) {
    return NativeObject();
  }
  return NativeObject(std::make_shared<NativeObjectStorage>(storage_->root_, pointer));
}

std::size_t NativeObject::object_count(NativeVectorField field) const noexcept {
  if (!is_valid() || field != NativeVectorField::messages) {
    return 0;
  }
  const auto *value = checked<api::messages>(storage_->object_);
  return value == nullptr ? 0 : value->messages_.size();
}

NativeObject NativeObject::object_at(NativeVectorField field, std::size_t index) const noexcept {
  if (!is_valid() || field != NativeVectorField::messages) {
    return NativeObject();
  }
  const auto *value = checked<api::messages>(storage_->object_);
  if (value == nullptr || index >= value->messages_.size() || value->messages_[index] == nullptr) {
    return NativeObject();
  }
  return NativeObject(std::make_shared<NativeObjectStorage>(storage_->root_, value->messages_[index].get()));
}

NativeBuffer NativeObject::string_value(NativeStringField field) const noexcept {
  if (!is_valid()) {
    return NativeBuffer();
  }
  const std::string *value = nullptr;
  switch (field) {
    case NativeStringField::option_value_string: {
      const auto *object = checked<api::optionValueString>(storage_->object_);
      value = object == nullptr ? nullptr : &object->value_;
      break;
    }
    case NativeStringField::error_message: {
      const auto *object = checked<api::error>(storage_->object_);
      value = object == nullptr ? nullptr : &object->message_;
      break;
    }
    case NativeStringField::formatted_text: {
      const auto *object = checked<api::formattedText>(storage_->object_);
      value = object == nullptr ? nullptr : &object->text_;
      break;
    }
  }
  if (value == nullptr) {
    return NativeBuffer();
  }
  return NativeBuffer(std::make_shared<NativeBufferStorage>(*value));
}

std::int32_t NativeObject::int32_value(NativeInt32Field field) const noexcept {
  if (!is_valid()) {
    return 0;
  }
  switch (field) {
    case NativeInt32Field::error_code: {
      const auto *value = checked<api::error>(storage_->object_);
      return value == nullptr ? 0 : value->code_;
    }
    case NativeInt32Field::messages_total_count: {
      const auto *value = checked<api::messages>(storage_->object_);
      return value == nullptr ? 0 : value->total_count_;
    }
  }
  return 0;
}

std::int64_t NativeObject::int64_value(NativeInt64Field field) const noexcept {
  const auto *value = is_valid() ? checked<api::message>(storage_->object_) : nullptr;
  if (value == nullptr) {
    return 0;
  }
  switch (field) {
    case NativeInt64Field::message_id: return value->id_;
    case NativeInt64Field::message_chat_id: return value->chat_id_;
  }
  return 0;
}

bool NativeObject::bool_field(std::int32_t index) const noexcept {
  return is_valid() ? generated_bool_field(storage_->object_, index) : false;
}

std::int32_t NativeObject::int32_field(std::int32_t index) const noexcept {
  return is_valid() ? generated_int32_field(storage_->object_, index) : 0;
}

std::int64_t NativeObject::int64_field(std::int32_t index) const noexcept {
  return is_valid() ? generated_int64_field(storage_->object_, index) : 0;
}

double NativeObject::double_field(std::int32_t index) const noexcept {
  return is_valid() ? generated_double_field(storage_->object_, index) : 0.0;
}

NativeBuffer NativeObject::buffer_field(std::int32_t index) const noexcept {
  const auto *value = is_valid() ? generated_buffer_field(storage_->object_, index) : nullptr;
  return value == nullptr
      ? NativeBuffer()
      : NativeBuffer(std::make_shared<NativeBufferStorage>(*value));
}

NativeObject NativeObject::object_field(std::int32_t index) const noexcept {
  const auto *value = is_valid() ? generated_object_field(storage_->object_, index) : nullptr;
  return value == nullptr
      ? NativeObject()
      : NativeObject(std::make_shared<NativeObjectStorage>(storage_->root_, value));
}

std::size_t NativeObject::vector_count(std::int32_t index) const noexcept {
  return is_valid() ? generated_vector_count(storage_->object_, index) : 0;
}

std::int32_t NativeObject::vector_int32_at(
    std::int32_t index, std::size_t element) const noexcept {
  return is_valid() ? generated_vector_int32_at(storage_->object_, index, element) : 0;
}

std::int64_t NativeObject::vector_int64_at(
    std::int32_t index, std::size_t element) const noexcept {
  return is_valid() ? generated_vector_int64_at(storage_->object_, index, element) : 0;
}

NativeBuffer NativeObject::vector_buffer_at(
    std::int32_t index, std::size_t element) const noexcept {
  const auto *value = is_valid()
      ? generated_vector_buffer_at(storage_->object_, index, element)
      : nullptr;
  return value == nullptr
      ? NativeBuffer()
      : NativeBuffer(std::make_shared<NativeBufferStorage>(*value));
}

NativeObject NativeObject::vector_object_at(
    std::int32_t index, std::size_t element) const noexcept {
  const auto *value = is_valid()
      ? generated_vector_object_at(storage_->object_, index, element)
      : nullptr;
  return value == nullptr
      ? NativeObject()
      : NativeObject(std::make_shared<NativeObjectStorage>(storage_->root_, value));
}

std::size_t NativeObject::nested_vector_count(
    std::int32_t index, std::size_t outer) const noexcept {
  return is_valid() ? generated_nested_vector_count(storage_->object_, index, outer) : 0;
}

NativeObject NativeObject::nested_vector_object_at(
    std::int32_t index,
    std::size_t outer,
    std::size_t inner) const noexcept {
  const auto *value = is_valid()
      ? generated_nested_vector_object_at(storage_->object_, index, outer, inner)
      : nullptr;
  return value == nullptr
      ? NativeObject()
      : NativeObject(std::make_shared<NativeObjectStorage>(storage_->root_, value));
}

NativeFunction::NativeFunction() noexcept = default;
NativeFunction::NativeFunction(const NativeFunction &) noexcept = default;
NativeFunction::NativeFunction(NativeFunction &&) noexcept = default;
NativeFunction &NativeFunction::operator=(const NativeFunction &) noexcept = default;
NativeFunction &NativeFunction::operator=(NativeFunction &&) noexcept = default;
NativeFunction::~NativeFunction() noexcept = default;

NativeFunction::NativeFunction(std::shared_ptr<NativeFunctionStorage> storage) noexcept : storage_(std::move(storage)) {
}

bool NativeFunction::is_valid() const noexcept {
  if (storage_ == nullptr) {
    return false;
  }
  std::lock_guard<std::mutex> lock(storage_->mutex_);
  return storage_->function_ != nullptr;
}

std::int32_t NativeFunction::type_id() const noexcept {
  if (storage_ == nullptr) {
    return 0;
  }
  std::lock_guard<std::mutex> lock(storage_->mutex_);
  return storage_->function_ == nullptr ? 0 : storage_->function_->get_id();
}

NativeResponse::NativeResponse() noexcept = default;
NativeResponse::NativeResponse(const NativeResponse &) noexcept = default;
NativeResponse::NativeResponse(NativeResponse &&) noexcept = default;
NativeResponse &NativeResponse::operator=(const NativeResponse &) noexcept = default;
NativeResponse &NativeResponse::operator=(NativeResponse &&) noexcept = default;
NativeResponse::~NativeResponse() noexcept = default;

NativeResponse::NativeResponse(
    std::int32_t client_id, std::uint64_t request_id, NativeObject object) noexcept
    : client_id_(client_id), request_id_(request_id), object_(std::move(object)) {
}

std::int32_t NativeResponse::client_id() const noexcept { return client_id_; }
std::uint64_t NativeResponse::request_id() const noexcept { return request_id_; }
NativeObject NativeResponse::object() const noexcept { return object_; }
bool NativeResponse::has_object() const noexcept { return object_.is_valid(); }

NativeFunction NativeFunctionFactory::get_option(NativeBuffer name) noexcept {
  auto value = api::make_object<api::getOption>();
  value->name_ = buffer_string(name);
  return NativeFunction(std::make_shared<NativeFunctionStorage>(std::move(value)));
}

NativeFunction NativeFunctionFactory::set_log_verbosity_level(std::int32_t level) noexcept {
  auto value = api::make_object<api::setLogVerbosityLevel>();
  value->new_verbosity_level_ = level;
  return NativeFunction(std::make_shared<NativeFunctionStorage>(std::move(value)));
}

NativeFunction NativeFunctionFactory::set_tdlib_parameters(
    bool use_test_dc,
    NativeBuffer database_directory,
    NativeBuffer files_directory,
    NativeBuffer database_encryption_key,
    bool use_file_database,
    bool use_chat_info_database,
    bool use_message_database,
    bool use_secret_chats,
    std::int32_t api_id,
    NativeBuffer api_hash,
    NativeBuffer system_language_code,
    NativeBuffer device_model,
    NativeBuffer system_version,
    NativeBuffer application_version) noexcept {
  auto value = api::make_object<api::setTdlibParameters>();
  value->use_test_dc_ = use_test_dc;
  value->database_directory_ = buffer_string(database_directory);
  value->files_directory_ = buffer_string(files_directory);
  value->database_encryption_key_ = buffer_string(database_encryption_key);
  value->use_file_database_ = use_file_database;
  value->use_chat_info_database_ = use_chat_info_database;
  value->use_message_database_ = use_message_database;
  value->use_secret_chats_ = use_secret_chats;
  value->api_id_ = api_id;
  value->api_hash_ = buffer_string(api_hash);
  value->system_language_code_ = buffer_string(system_language_code);
  value->device_model_ = buffer_string(device_model);
  value->system_version_ = buffer_string(system_version);
  value->application_version_ = buffer_string(application_version);
  return NativeFunction(std::make_shared<NativeFunctionStorage>(std::move(value)));
}

NativeFunction NativeFunctionFactory::get_chat_history(
    std::int64_t chat_id,
    std::int64_t from_message_id,
    std::int32_t offset,
    std::int32_t limit,
    bool only_local) noexcept {
  auto value = api::make_object<api::getChatHistory>();
  value->chat_id_ = chat_id;
  value->from_message_id_ = from_message_id;
  value->offset_ = offset;
  value->limit_ = limit;
  value->only_local_ = only_local;
  return NativeFunction(std::make_shared<NativeFunctionStorage>(std::move(value)));
}

NativeFunction NativeFunctionFactory::close() noexcept {
  return NativeFunction(std::make_shared<NativeFunctionStorage>(api::make_object<api::close>()));
}

NativeBufferArray::NativeBufferArray() noexcept
    : storage_(std::make_shared<NativeBufferArrayStorage>()) {
}
NativeBufferArray::NativeBufferArray(const NativeBufferArray &) noexcept = default;
NativeBufferArray::NativeBufferArray(NativeBufferArray &&) noexcept = default;
NativeBufferArray &NativeBufferArray::operator=(const NativeBufferArray &) noexcept = default;
NativeBufferArray &NativeBufferArray::operator=(NativeBufferArray &&) noexcept = default;
NativeBufferArray::~NativeBufferArray() noexcept = default;

void NativeBufferArray::append(NativeBuffer value) noexcept {
  if (storage_ != nullptr) {
    storage_->values_.push_back(buffer_string(value));
  }
}

std::size_t NativeBufferArray::size() const noexcept {
  return storage_ == nullptr ? 0 : storage_->values_.size();
}

NativeObjectArray::NativeObjectArray() noexcept
    : storage_(std::make_shared<NativeObjectArrayStorage>()) {
}
NativeObjectArray::NativeObjectArray(const NativeObjectArray &) noexcept = default;
NativeObjectArray::NativeObjectArray(NativeObjectArray &&) noexcept = default;
NativeObjectArray &NativeObjectArray::operator=(const NativeObjectArray &) noexcept = default;
NativeObjectArray &NativeObjectArray::operator=(NativeObjectArray &&) noexcept = default;
NativeObjectArray::~NativeObjectArray() noexcept = default;

void NativeObjectArray::append(NativeObject value) noexcept {
  if (storage_ != nullptr) {
    storage_->values_.push_back(std::move(value));
  }
}

std::size_t NativeObjectArray::size() const noexcept {
  return storage_ == nullptr ? 0 : storage_->values_.size();
}

NativeObjectArrayArray::NativeObjectArrayArray() noexcept
    : storage_(std::make_shared<NativeObjectArrayArrayStorage>()) {
}
NativeObjectArrayArray::NativeObjectArrayArray(const NativeObjectArrayArray &) noexcept = default;
NativeObjectArrayArray::NativeObjectArrayArray(NativeObjectArrayArray &&) noexcept = default;
NativeObjectArrayArray &NativeObjectArrayArray::operator=(
    const NativeObjectArrayArray &) noexcept = default;
NativeObjectArrayArray &NativeObjectArrayArray::operator=(NativeObjectArrayArray &&) noexcept = default;
NativeObjectArrayArray::~NativeObjectArrayArray() noexcept = default;

void NativeObjectArrayArray::append(NativeObjectArray value) noexcept {
  if (storage_ != nullptr && value.storage_ != nullptr) {
    storage_->values_.push_back(value.storage_->values_);
  }
}

std::size_t NativeObjectArrayArray::size() const noexcept {
  return storage_ == nullptr ? 0 : storage_->values_.size();
}

NativeArguments::NativeArguments() noexcept
    : storage_(std::make_shared<NativeArgumentsStorage>()) {
}
NativeArguments::NativeArguments(const NativeArguments &) noexcept = default;
NativeArguments::NativeArguments(NativeArguments &&) noexcept = default;
NativeArguments &NativeArguments::operator=(const NativeArguments &) noexcept = default;
NativeArguments &NativeArguments::operator=(NativeArguments &&) noexcept = default;
NativeArguments::~NativeArguments() noexcept = default;

void NativeArguments::append_bool(bool value) noexcept {
  if (storage_ != nullptr) storage_->values_.emplace_back(value);
}
void NativeArguments::append_int32(std::int32_t value) noexcept {
  if (storage_ != nullptr) storage_->values_.emplace_back(value);
}
void NativeArguments::append_int64(std::int64_t value) noexcept {
  if (storage_ != nullptr) storage_->values_.emplace_back(value);
}
void NativeArguments::append_double(double value) noexcept {
  if (storage_ != nullptr) storage_->values_.emplace_back(value);
}
void NativeArguments::append_buffer(NativeBuffer value) noexcept {
  if (storage_ != nullptr) storage_->values_.emplace_back(buffer_string(value));
}
void NativeArguments::append_object(NativeObject value) noexcept {
  if (storage_ != nullptr) storage_->values_.emplace_back(std::move(value));
}
void NativeArguments::append_int32_vector(
    const std::int32_t *values, std::size_t count) noexcept {
  if (storage_ == nullptr) return;
  storage_->values_.emplace_back(
      values == nullptr ? NativeInt32Vector() : NativeInt32Vector(values, values + count));
}
void NativeArguments::append_int64_vector(
    const std::int64_t *values, std::size_t count) noexcept {
  if (storage_ == nullptr) return;
  storage_->values_.emplace_back(
      values == nullptr ? NativeInt64Vector() : NativeInt64Vector(values, values + count));
}
void NativeArguments::append_buffer_vector(NativeBufferArray values) noexcept {
  if (storage_ != nullptr) {
    storage_->values_.emplace_back(
        values.storage_ == nullptr ? NativeBufferVector() : values.storage_->values_);
  }
}
void NativeArguments::append_object_vector(NativeObjectArray values) noexcept {
  if (storage_ != nullptr) {
    storage_->values_.emplace_back(
        values.storage_ == nullptr ? NativeObjectVector() : values.storage_->values_);
  }
}
void NativeArguments::append_nested_object_vector(NativeObjectArrayArray values) noexcept {
  if (storage_ != nullptr) {
    storage_->values_.emplace_back(
        values.storage_ == nullptr ? NativeNestedObjectVector() : values.storage_->values_);
  }
}
std::size_t NativeArguments::size() const noexcept {
  return storage_ == nullptr ? 0 : storage_->values_.size();
}

NativeObject NativeSchemaFactory::make_object(
    std::int32_t type_id, NativeArguments arguments) noexcept {
  if (arguments.storage_ == nullptr) {
    return NativeObject();
  }
  return NativeObjectFactoryAccess::make(
      generated_make_schema_object(type_id, *arguments.storage_));
}

NativeFunction NativeSchemaFactory::make_function(
    std::int32_t type_id, NativeArguments arguments) noexcept {
  if (arguments.storage_ == nullptr) {
    return NativeFunction();
  }
  auto function = generated_make_schema_function(type_id, *arguments.storage_);
  return function == nullptr
      ? NativeFunction()
      : NativeFunction(std::make_shared<NativeFunctionStorage>(std::move(function)));
}

NativeManager::NativeManager() noexcept : storage_(std::make_shared<NativeManagerStorage>()) {
}
NativeManager::NativeManager(const NativeManager &) noexcept = default;
NativeManager::NativeManager(NativeManager &&) noexcept = default;
NativeManager &NativeManager::operator=(const NativeManager &) noexcept = default;
NativeManager &NativeManager::operator=(NativeManager &&) noexcept = default;
NativeManager::~NativeManager() noexcept = default;

bool NativeManager::is_valid() const noexcept { return storage_ != nullptr; }

std::int32_t NativeManager::create_client_id() noexcept {
  return storage_ == nullptr ? 0 : storage_->manager_.create_client_id();
}

bool NativeManager::send(
    std::int32_t client_id, std::uint64_t request_id, NativeFunction request) noexcept {
  if (storage_ == nullptr || request_id == 0 || request.storage_ == nullptr) {
    return false;
  }
  auto function = request.storage_->take();
  if (function == nullptr) {
    return false;
  }
  storage_->manager_.send(client_id, request_id, std::move(function));
  return true;
}

NativeResponse NativeManager::receive(double timeout_seconds) noexcept {
  if (storage_ == nullptr) {
    return NativeResponse();
  }
  auto response = storage_->manager_.receive(timeout_seconds);
  return NativeResponse(
      response.client_id,
      response.request_id,
      NativeObjectFactoryAccess::make(std::move(response.object)));
}

NativeObject NativeManager::execute(NativeFunction request) noexcept {
  if (request.storage_ == nullptr) {
    return NativeObject();
  }
  auto function = request.storage_->take();
  if (function == nullptr) {
    return NativeObject();
  }
  return NativeObjectFactoryAccess::make(td::ClientManager::execute(std::move(function)));
}

}  // namespace tdlibkit

#pragma GCC visibility pop
