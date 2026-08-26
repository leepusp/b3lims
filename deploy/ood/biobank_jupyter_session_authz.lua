require "apache2"

local BINDING_ROOT = "/run/biobank-jupyter-proxy"

-- The reconciler runs every 30 seconds.
-- 120 seconds tolerates transient scheduler/controller delays while
-- ensuring a failed reconciler eventually fails closed.
local MAX_LEASE_AGE = 120
local MAX_FUTURE_SKEW = 10

local ALLOWED_HOSTS = {
    n01 = true,
    gn01 = true,
    gn02 = true,
    gn03 = true,
}

local BINDING_KEYS = {
    version = true,
    notebook_id = true,
    owner = true,
    run_id = true,
    job_id = true,
    host = true,
    port = true,
}

local LEASE_KEYS = {
    version = true,
    notebook_id = true,
    owner = true,
    run_id = true,
    job_id = true,
    host = true,
    port = true,
    validated_at = true,
}

local function deny()
    return apache2.AUTHZ_DENIED
end

local function read_record(
    path,
    required_keys
)
    local handle = io.open(
        path,
        "r"
    )

    if not handle then
        return nil
    end

    local values = {}

    for line in handle:lines() do
        local key, value = string.match(
            line,
            "^([a-z_]+)=(.*)$"
        )

        if (
            not key
            or not required_keys[key]
            or values[key] ~= nil
        ) then
            handle:close()
            return nil
        end

        values[key] = value
    end

    handle:close()

    for key, _ in pairs(
        required_keys
    ) do
        if values[key] == nil then
            return nil
        end
    end

    return values
end

local function valid_owner(owner)
    return (
        owner ~= ""
        and #owner <= 64
        and string.match(
            owner,
            "^[A-Za-z0-9][A-Za-z0-9_.-]*$"
        ) ~= nil
    )
end

local function valid_run_id(run_id)
    return (
        run_id ~= ""
        and string.match(
            run_id,
            "^[A-Za-z0-9_-]+$"
        ) ~= nil
    )
end

function biobank_jupyter_session_authz(r)
    local uri = r.uri or ""

    local notebook_id, host, port = string.match(
        uri,
        "^/biobank/internal/lab%-tools/jupyter/"
        .. "(%d+)/node/([^/]+)/(%d+)/"
    )

    if (
        not notebook_id
        or not host
        or not port
    ) then
        return deny()
    end

    if #notebook_id > 20 then
        return deny()
    end

    if not ALLOWED_HOSTS[host] then
        return deny()
    end

    local numeric_port = tonumber(
        port
    )

    if (
        not numeric_port
        or numeric_port < 1024
        or numeric_port > 65535
    ) then
        return deny()
    end

    local binding_path = (
        BINDING_ROOT
        .. "/notebook_"
        .. notebook_id
        .. ".binding"
    )

    local lease_path = (
        BINDING_ROOT
        .. "/notebook_"
        .. notebook_id
        .. ".lease"
    )

    local binding = read_record(
        binding_path,
        BINDING_KEYS
    )

    if not binding then
        return deny()
    end

    if binding.version ~= "1" then
        return deny()
    end

    if binding.notebook_id ~= notebook_id then
        return deny()
    end

    if not valid_owner(
        binding.owner
    ) then
        return deny()
    end

    if not valid_run_id(
        binding.run_id
    ) then
        return deny()
    end

    if not string.match(
        binding.job_id,
        "^%d+$"
    ) then
        return deny()
    end

    if binding.host ~= host then
        return deny()
    end

    if binding.port ~= port then
        return deny()
    end

    local lease = read_record(
        lease_path,
        LEASE_KEYS
    )

    if not lease then
        return deny()
    end

    if lease.version ~= "1" then
        return deny()
    end

    -- The lease must describe the exact binding that was validated.
    for _, key in ipairs({
        "notebook_id",
        "owner",
        "run_id",
        "job_id",
        "host",
        "port",
    }) do
        if lease[key] ~= binding[key] then
            return deny()
        end
    end

    if not string.match(
        lease.validated_at,
        "^%d+$"
    ) then
        return deny()
    end

    local validated_at = tonumber(
        lease.validated_at
    )

    local now = os.time()

    if (
        not validated_at
        or validated_at > (
            now + MAX_FUTURE_SKEW
        )
        or (
            now - validated_at
        ) > MAX_LEASE_AGE
    ) then
        return deny()
    end

    return apache2.AUTHZ_GRANTED
end
