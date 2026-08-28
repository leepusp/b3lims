local STATE_ROOT =
    "/run/biobank-auth-guard"

local MAX_IP_LENGTH = 64
local MAX_STATE_BYTES = 512


local function client_ip(r)
    local value =
        r.useragent_ip
        or ""

    if type(value) ~= "string" then
        return nil
    end

    if value == "" then
        return nil
    end

    if #value > MAX_IP_LENGTH then
        return nil
    end

    if not string.match(
        value,
        "^[0-9A-Fa-f:.]+$"
    ) then
        return nil
    end

    return string.lower(
        value
    )
end


local function is_banned(ip)
    local path =
        STATE_ROOT
        .. "/"
        .. ip

    local handle =
        io.open(
            path,
            "r"
        )

    if not handle then
        return false
    end

    local data =
        handle:read(
            "*a"
        )
        or ""

    handle:close()

    -- Root writes state atomically. If an existing state file is
    -- malformed, fail closed for that address rather than allowing
    -- the enforcement boundary to be bypassed.
    if #data > MAX_STATE_BYTES then
        return true
    end

    local stored_ip, expires_at =
        string.match(
            data,
            "^version=1\n"
            .. "ip=([0-9A-Fa-f:.]+)\n"
            .. "expires_at=(%d+)\n?$"
        )

    if not stored_ip then
        return true
    end

    if string.lower(
        stored_ip
    ) ~= ip then
        return true
    end

    local expiry =
        tonumber(
            expires_at
        )

    if not expiry then
        return true
    end

    -- Expiration is evaluated by Apache as well as Fail2ban.
    -- Therefore stale state left behind by an interrupted detector
    -- cannot cause an indefinite B3 LIMS ban.
    if expiry <= os.time() then
        return false
    end

    return true
end


function biobank_auth_guard(r)
    local ip =
        client_ip(r)

    -- A malformed or unavailable direct client address is rejected
    -- rather than allowing an ambiguous authentication origin.
    if not ip then
        r:custom_response(
            403,
            "Forbidden"
        )

        return 403
    end

    if is_banned(ip) then
        r:custom_response(
            403,
            "Forbidden"
        )

        return 403
    end

    return apache2.DECLINED
end
