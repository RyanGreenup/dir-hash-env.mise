local cmd = require("cmd")

local DEFAULT_KEY = "PORT"
local DEFAULT_RANGE_START = 20000
local DEFAULT_RANGE_SIZE = 20000

local function integer_option(options, name, default)
    local value = options[name]
    if value == nil then
        return default
    end

    if type(value) ~= "number" or value % 1 ~= 0 then
        error(name .. " must be an integer")
    end

    return value
end

local function env_keys(options)
    if options.keys ~= nil then
        if type(options.keys) ~= "table" or #options.keys == 0 then
            error("keys must be a non-empty array of environment variable names")
        end
        return options.keys
    end

    return { options.key or DEFAULT_KEY }
end

local function validate_key(key)
    if type(key) ~= "string" or not key:match("^[A-Za-z_][A-Za-z0-9_]*$") then
        error("invalid environment variable name: " .. tostring(key))
    end
end

local function project_path(options)
    local path = options.path or os.getenv("MISE_PROJECT_ROOT") or os.getenv("PWD")
    if not path or path == "" then
        error("could not determine the project path; set the path option explicitly")
    end
    return path
end

local function salt_option(options)
    local salt = options.salt
    if salt ~= nil and type(salt) ~= "string" then
        error("salt must be a string")
    end
    return salt
end

local function sha256_prefix(path, salt)
    -- Pass the values through the environment instead of interpolating them into
    -- the command, so shell metacharacters remain safe. A NUL separator makes
    -- the salted input unambiguous while leaving unsalted hashes unchanged.
    local hash_input_command = [[printf '%s' "$MISE_DETERMINISTIC_PORT_INPUT"]]
    local command_env = { MISE_DETERMINISTIC_PORT_INPUT = path }
    if salt ~= nil and salt ~= "" then
        hash_input_command = [[printf '%s\0%s' "$MISE_DETERMINISTIC_PORT_INPUT" "$MISE_DETERMINISTIC_PORT_SALT"]]
        command_env.MISE_DETERMINISTIC_PORT_SALT = salt
    end

    local hash_command =
        [[if command -v sha256sum >/dev/null 2>&1; then sha256sum; elif command -v shasum >/dev/null 2>&1; then shasum -a 256; else echo 'deterministic-port requires sha256sum or shasum' >&2; exit 1; fi]]
    local output = cmd.exec(hash_input_command .. " | " .. hash_command, { env = command_env })
    local prefix = output:match("^([0-9a-fA-F][0-9a-fA-F][0-9a-fA-F][0-9a-fA-F])")
    if not prefix then
        error("failed to calculate the project path hash")
    end
    return tonumber(prefix, 16)
end

---Set one or more deterministic port environment variables for this project.
---@param ctx MiseEnvCtx
---@return EnvKey[]
function PLUGIN:MiseEnv(ctx)
    local options = ctx.options or {}
    local range_start = integer_option(options, "range_start", DEFAULT_RANGE_START)
    local range_size = integer_option(options, "range_size", DEFAULT_RANGE_SIZE)
    local keys = env_keys(options)
    local salt = salt_option(options)

    if range_start < 1 or range_start > 65535 then
        error("range_start must be between 1 and 65535")
    end
    if range_size < #keys then
        error("range_size must be at least the number of requested keys")
    end
    if range_start + range_size - 1 > 65535 then
        error("the configured port range must end at or before 65535")
    end

    local base_offset = sha256_prefix(project_path(options), salt) % range_size
    local result = {}
    for index, key in ipairs(keys) do
        validate_key(key)
        -- Linear probing keeps ports unique if the base value is near the end
        -- of the configured range.
        local offset = (base_offset + index - 1) % range_size
        table.insert(result, { key = key, value = tostring(range_start + offset) })
    end

    return result
end
