require "apache2"

local BINDING_ROOT = "/run/biobank-jupyter-proxy"

local PROXY_COOKIE_NAME =
    "__Secure-biobank-jupyter-token"

-- The reconciler runs every 30 seconds.
-- 120 seconds allows transient scheduler delays while ensuring
-- that a failed reconciler eventually fails closed.
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

    for key, _ in pairs(required_keys) do
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


local function valid_proxy_token(token)
    return (
        token ~= nil
        and #token >= 32
        and #token <= 256
        and string.match(
            token,
            "^[A-Za-z0-9_-]+$"
        ) ~= nil
    )
end


local function request_tuple(r)
    local uri = r.uri or ""

    local notebook_id, host, port =
        string.match(
            uri,
            "^/c3%-lims/internal/lab%-tools/jupyter/"
            .. "(%d+)/node/([^/]+)/(%d+)/"
        )

    if (
        not notebook_id
        or not host
        or not port
    ) then
        return nil
    end

    if #notebook_id > 20 then
        return nil
    end

    if not ALLOWED_HOSTS[host] then
        return nil
    end

    local numeric_port = tonumber(port)

    if (
        not numeric_port
        or numeric_port < 1024
        or numeric_port > 65535
    ) then
        return nil
    end

    return notebook_id, host, port
end


local function extract_proxy_cookie(cookie_header)
    if (
        cookie_header == nil
        or cookie_header == ""
    ) then
        return nil, nil
    end

    local token = nil
    local retained = {}
    local prefix = PROXY_COOKIE_NAME .. "="

    for raw_part in string.gmatch(
        cookie_header .. ";",
        "([^;]*);"
    ) do
        local part = string.match(
            raw_part,
            "^%s*(.-)%s*$"
        )

        if part ~= "" then
            if string.sub(
                part,
                1,
                #prefix
            ) == prefix then
                if token ~= nil then
                    return nil, nil
                end

                token = string.sub(
                    part,
                    #prefix + 1
                )
            else
                table.insert(
                    retained,
                    part
                )
            end
        end
    end

    if not valid_proxy_token(token) then
        return nil, nil
    end

    return token, table.concat(
        retained,
        "; "
    )
end


local function binding_is_authorized(
    notebook_id,
    host,
    port
)
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
        return false
    end

    if binding.version ~= "1" then
        return false
    end

    if (
        binding.notebook_id
        ~= notebook_id
    ) then
        return false
    end

    if not valid_owner(
        binding.owner
    ) then
        return false
    end

    if not valid_run_id(
        binding.run_id
    ) then
        return false
    end

    if not string.match(
        binding.job_id,
        "^%d+$"
    ) then
        return false
    end

    if binding.host ~= host then
        return false
    end

    if binding.port ~= port then
        return false
    end

    local lease = read_record(
        lease_path,
        LEASE_KEYS
    )

    if not lease then
        return false
    end

    if lease.version ~= "1" then
        return false
    end

    for _, key in ipairs({
        "notebook_id",
        "owner",
        "run_id",
        "job_id",
        "host",
        "port",
    }) do
        if lease[key] ~= binding[key] then
            return false
        end
    end

    if not string.match(
        lease.validated_at,
        "^%d+$"
    ) then
        return false
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
        return false
    end

    return true
end


function biobank_jupyter_session_authz(r)
    local notebook_id, host, port =
        request_tuple(r)

    if not notebook_id then
        return deny()
    end

    if not binding_is_authorized(
        notebook_id,
        host,
        port
    ) then
        return deny()
    end

    local token, _ = extract_proxy_cookie(
        r.headers_in["Cookie"]
    )

    if not token then
        return deny()
    end

    return apache2.AUTHZ_GRANTED
end


function biobank_jupyter_proxy(r)
    local notebook_id, host, port =
        request_tuple(r)

    if not notebook_id then
        r:custom_response(
            403,
            "Forbidden"
        )
        return 403
    end

    local token, retained_cookie =
        extract_proxy_cookie(
            r.headers_in["Cookie"]
        )

    if not token then
        r:custom_response(
            403,
            "Forbidden"
        )
        return 403
    end

    -- The browser never sends the native Jupyter bearer token
    -- through the Authorization header. The Biobank proxy injects
    -- it only after the exact active-session authorization succeeds.
    r.headers_in["Authorization"] =
        "token " .. token

    -- Do not disclose the bootstrap bearer token to Jupyter as
    -- an application cookie. Preserve unrelated Jupyter cookies.
    r.headers_in["Cookie"] =
        retained_cookie or ""

    -- Never forward browser-supplied Biobank identity metadata
    -- into the compute-node server.
    r.headers_in["X-Biobank-Pam-User"] = ""
    r.headers_in["X-Forwarded-User"] = ""

    r.headers_in["X-Forwarded-Proto"] =
        r.is_https and "https" or "http"

    local upgrade = string.lower(
        r.headers_in["Upgrade"] or ""
    )

    local protocol = "http://"

    if upgrade == "websocket" then
        protocol = "ws://"
    end

    -- Delegate the transport itself to Apache mod_proxy.
    -- This is the minimal operation previously supplied by
    -- Open OnDemand's proxy helper, but is now Biobank-owned.
    r.handler = (
        "proxy:"
        .. protocol
        .. host
        .. ":"
        .. port
    )

    -- r.uri does not contain the query string. Apache retains
    -- ordinary request arguments separately while ensuring the
    -- native Jupyter bearer token never appears in the URL.
    local uri = r.uri or "/"

    if uri == "" then
        uri = "/"
    end

    r.filename = uri

    r:custom_response(
        503,
        "Failed to connect to managed Jupyter server."
    )

    return apache2.DECLINED
end
