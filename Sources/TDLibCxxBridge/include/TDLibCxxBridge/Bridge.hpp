#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>

#if defined(_WIN32)
#define TDLIBKIT_BRIDGE_EXPORT
#else
#define TDLIBKIT_BRIDGE_EXPORT __attribute__((visibility("default")))
#endif

namespace tdlibkit {

struct NativeBufferStorage;
struct NativeFunctionStorage;
struct NativeObjectStorage;
struct NativeManagerStorage;
struct NativeObjectFactoryAccess;
struct NativeArgumentsStorage;
struct NativeBufferArrayStorage;
struct NativeObjectArrayStorage;
struct NativeObjectArrayArrayStorage;
struct NativeArgumentAccess;

class TDLIBKIT_BRIDGE_EXPORT NativeBuffer final {
 public:
  NativeBuffer() noexcept;
  NativeBuffer(const NativeBuffer &) noexcept;
  NativeBuffer(NativeBuffer &&) noexcept;
  NativeBuffer &operator=(const NativeBuffer &) noexcept;
  NativeBuffer &operator=(NativeBuffer &&) noexcept;
  ~NativeBuffer() noexcept;

  static NativeBuffer copy(const std::uint8_t *bytes, std::size_t count) noexcept;
  std::size_t size() const noexcept;
  std::size_t copy_to(std::uint8_t *destination, std::size_t capacity) const noexcept;

 private:
  explicit NativeBuffer(std::shared_ptr<NativeBufferStorage> storage) noexcept;
  std::shared_ptr<NativeBufferStorage> storage_;

  friend class NativeFunctionFactory;
  friend class NativeObject;
};

enum class NativeObjectKind : std::int32_t {
  unknown = 0,
  error = 1,
  ok = 2,
  option_value_string = 3,
  update_authorization_state = 4,
  update_new_message = 5,
  authorization_state_wait_tdlib_parameters = 6,
  authorization_state_wait_phone_number = 7,
  authorization_state_ready = 8,
  authorization_state_logging_out = 9,
  authorization_state_closing = 10,
  authorization_state_closed = 11,
  messages = 12,
  message = 13,
  message_text = 14,
  formatted_text = 15
};

enum class NativeChildField : std::int32_t {
  update_authorization_state = 1,
  update_new_message = 2,
  message_content = 3,
  message_text_text = 4
};

enum class NativeVectorField : std::int32_t {
  messages = 1
};

enum class NativeStringField : std::int32_t {
  option_value_string = 1,
  error_message = 2,
  formatted_text = 3
};

enum class NativeInt32Field : std::int32_t {
  error_code = 1,
  messages_total_count = 2
};

enum class NativeInt64Field : std::int32_t {
  message_id = 1,
  message_chat_id = 2
};

class TDLIBKIT_BRIDGE_EXPORT NativeObject final {
 public:
  NativeObject() noexcept;
  NativeObject(const NativeObject &) noexcept;
  NativeObject(NativeObject &&) noexcept;
  NativeObject &operator=(const NativeObject &) noexcept;
  NativeObject &operator=(NativeObject &&) noexcept;
  ~NativeObject() noexcept;

  bool is_valid() const noexcept;
  std::int32_t type_id() const noexcept;
  NativeObjectKind kind() const noexcept;
  NativeObject child(NativeChildField field) const noexcept;
  std::size_t object_count(NativeVectorField field) const noexcept;
  NativeObject object_at(NativeVectorField field, std::size_t index) const noexcept;
  NativeBuffer string_value(NativeStringField field) const noexcept;
  std::int32_t int32_value(NativeInt32Field field) const noexcept;
  std::int64_t int64_value(NativeInt64Field field) const noexcept;

  bool bool_field(std::int32_t index) const noexcept;
  std::int32_t int32_field(std::int32_t index) const noexcept;
  std::int64_t int64_field(std::int32_t index) const noexcept;
  double double_field(std::int32_t index) const noexcept;
  NativeBuffer buffer_field(std::int32_t index) const noexcept;
  NativeObject object_field(std::int32_t index) const noexcept;
  std::size_t vector_count(std::int32_t index) const noexcept;
  std::int32_t vector_int32_at(std::int32_t index, std::size_t element) const noexcept;
  std::int64_t vector_int64_at(std::int32_t index, std::size_t element) const noexcept;
  NativeBuffer vector_buffer_at(std::int32_t index, std::size_t element) const noexcept;
  NativeObject vector_object_at(std::int32_t index, std::size_t element) const noexcept;
  std::size_t nested_vector_count(std::int32_t index, std::size_t outer) const noexcept;
  NativeObject nested_vector_object_at(
      std::int32_t index,
      std::size_t outer,
      std::size_t inner) const noexcept;

 private:
  explicit NativeObject(std::shared_ptr<NativeObjectStorage> storage) noexcept;
  std::shared_ptr<NativeObjectStorage> storage_;

  friend class NativeManager;
  friend class NativeSchemaFactory;
  friend struct NativeObjectFactoryAccess;
  friend struct NativeArgumentAccess;
};

class TDLIBKIT_BRIDGE_EXPORT NativeFunction final {
 public:
  NativeFunction() noexcept;
  NativeFunction(const NativeFunction &) noexcept;
  NativeFunction(NativeFunction &&) noexcept;
  NativeFunction &operator=(const NativeFunction &) noexcept;
  NativeFunction &operator=(NativeFunction &&) noexcept;
  ~NativeFunction() noexcept;

  bool is_valid() const noexcept;
  std::int32_t type_id() const noexcept;

 private:
  explicit NativeFunction(std::shared_ptr<NativeFunctionStorage> storage) noexcept;
  std::shared_ptr<NativeFunctionStorage> storage_;

  friend class NativeFunctionFactory;
  friend class NativeManager;
  friend class NativeSchemaFactory;
};

class TDLIBKIT_BRIDGE_EXPORT NativeResponse final {
 public:
  NativeResponse() noexcept;
  NativeResponse(const NativeResponse &) noexcept;
  NativeResponse(NativeResponse &&) noexcept;
  NativeResponse &operator=(const NativeResponse &) noexcept;
  NativeResponse &operator=(NativeResponse &&) noexcept;
  ~NativeResponse() noexcept;

  std::int32_t client_id() const noexcept;
  std::uint64_t request_id() const noexcept;
  NativeObject object() const noexcept;
  bool has_object() const noexcept;

 private:
  NativeResponse(std::int32_t client_id, std::uint64_t request_id, NativeObject object) noexcept;
  std::int32_t client_id_{0};
  std::uint64_t request_id_{0};
  NativeObject object_;

  friend class NativeManager;
};

class TDLIBKIT_BRIDGE_EXPORT NativeFunctionFactory final {
 public:
  static NativeFunction get_option(NativeBuffer name) noexcept;
  static NativeFunction set_log_verbosity_level(std::int32_t level) noexcept;
  static NativeFunction set_tdlib_parameters(
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
      NativeBuffer application_version) noexcept;
  static NativeFunction get_chat_history(
      std::int64_t chat_id,
      std::int64_t from_message_id,
      std::int32_t offset,
      std::int32_t limit,
      bool only_local) noexcept;
  static NativeFunction close() noexcept;
};

class TDLIBKIT_BRIDGE_EXPORT NativeBufferArray final {
 public:
  NativeBufferArray() noexcept;
  NativeBufferArray(const NativeBufferArray &) noexcept;
  NativeBufferArray(NativeBufferArray &&) noexcept;
  NativeBufferArray &operator=(const NativeBufferArray &) noexcept;
  NativeBufferArray &operator=(NativeBufferArray &&) noexcept;
  ~NativeBufferArray() noexcept;

  void append(NativeBuffer value) noexcept;
  std::size_t size() const noexcept;

 private:
  std::shared_ptr<NativeBufferArrayStorage> storage_;
  friend class NativeArguments;
};

class TDLIBKIT_BRIDGE_EXPORT NativeObjectArray final {
 public:
  NativeObjectArray() noexcept;
  NativeObjectArray(const NativeObjectArray &) noexcept;
  NativeObjectArray(NativeObjectArray &&) noexcept;
  NativeObjectArray &operator=(const NativeObjectArray &) noexcept;
  NativeObjectArray &operator=(NativeObjectArray &&) noexcept;
  ~NativeObjectArray() noexcept;

  void append(NativeObject value) noexcept;
  std::size_t size() const noexcept;

 private:
  std::shared_ptr<NativeObjectArrayStorage> storage_;
  friend class NativeArguments;
  friend class NativeObjectArrayArray;
};

class TDLIBKIT_BRIDGE_EXPORT NativeObjectArrayArray final {
 public:
  NativeObjectArrayArray() noexcept;
  NativeObjectArrayArray(const NativeObjectArrayArray &) noexcept;
  NativeObjectArrayArray(NativeObjectArrayArray &&) noexcept;
  NativeObjectArrayArray &operator=(const NativeObjectArrayArray &) noexcept;
  NativeObjectArrayArray &operator=(NativeObjectArrayArray &&) noexcept;
  ~NativeObjectArrayArray() noexcept;

  void append(NativeObjectArray value) noexcept;
  std::size_t size() const noexcept;

 private:
  std::shared_ptr<NativeObjectArrayArrayStorage> storage_;
  friend class NativeArguments;
};

class TDLIBKIT_BRIDGE_EXPORT NativeArguments final {
 public:
  NativeArguments() noexcept;
  NativeArguments(const NativeArguments &) noexcept;
  NativeArguments(NativeArguments &&) noexcept;
  NativeArguments &operator=(const NativeArguments &) noexcept;
  NativeArguments &operator=(NativeArguments &&) noexcept;
  ~NativeArguments() noexcept;

  void append_bool(bool value) noexcept;
  void append_int32(std::int32_t value) noexcept;
  void append_int64(std::int64_t value) noexcept;
  void append_double(double value) noexcept;
  void append_buffer(NativeBuffer value) noexcept;
  void append_object(NativeObject value) noexcept;
  void append_int32_vector(const std::int32_t *values, std::size_t count) noexcept;
  void append_int64_vector(const std::int64_t *values, std::size_t count) noexcept;
  void append_buffer_vector(NativeBufferArray values) noexcept;
  void append_object_vector(NativeObjectArray values) noexcept;
  void append_nested_object_vector(NativeObjectArrayArray values) noexcept;
  std::size_t size() const noexcept;

 private:
  std::shared_ptr<NativeArgumentsStorage> storage_;
  friend class NativeSchemaFactory;
  friend struct NativeArgumentAccess;
};

class TDLIBKIT_BRIDGE_EXPORT NativeSchemaFactory final {
 public:
  static NativeObject make_object(std::int32_t type_id, NativeArguments arguments) noexcept;
  static NativeFunction make_function(std::int32_t type_id, NativeArguments arguments) noexcept;
};

class TDLIBKIT_BRIDGE_EXPORT NativeManager final {
 public:
  NativeManager() noexcept;
  NativeManager(const NativeManager &) noexcept;
  NativeManager(NativeManager &&) noexcept;
  NativeManager &operator=(const NativeManager &) noexcept;
  NativeManager &operator=(NativeManager &&) noexcept;
  ~NativeManager() noexcept;

  bool is_valid() const noexcept;
  std::int32_t create_client_id() noexcept;
  bool send(std::int32_t client_id, std::uint64_t request_id, NativeFunction request) noexcept;
  NativeResponse receive(double timeout_seconds) noexcept;
  static NativeObject execute(NativeFunction request) noexcept;

 private:
  std::shared_ptr<NativeManagerStorage> storage_;
};

}  // namespace tdlibkit

#undef TDLIBKIT_BRIDGE_EXPORT
