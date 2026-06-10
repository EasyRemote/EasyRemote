/*
 * easyremote fast forwarder — the low-latency interim path (SPEC D2).
 *
 * stdin(args JSON) -> warm-host Unix socket -> stdout(result JSON).
 * Replaces the Python shim's ~50-60ms interpreter spawn with a
 * single-digit-millisecond native spawn; removed entirely once the
 * daemon host-attach protocol (Cli PR-1) lands.
 *
 * Response slicing relies on the host's PINNED serialization prefixes
 * (tests/test_host.py::test_wire_prefixes_are_pinned_for_the_c_forwarder):
 *   {"ok":true,"result":<json>}   ->  print <json>, exit 0
 *   {"ok":false,"error":<json>}   ->  print <json> to stderr, exit 1
 *
 * Build: cc -O2 -o easyremote-forward forward.c   (done lazily by
 * easyremote._host.fastpath; Python shim remains the fallback).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

static int fail(const char *msg) {
    fprintf(stderr, "%s\n", msg);
    return 1;
}

static char *read_all(FILE *stream, size_t *out_len) {
    size_t cap = 1 << 16, len = 0, n;
    char *buf = malloc(cap);
    if (!buf) return NULL;
    while ((n = fread(buf + len, 1, cap - len - 1, stream)) > 0) {
        len += n;
        if (len + 1 >= cap) {
            char *grown = realloc(buf, cap *= 2);
            if (!grown) { free(buf); return NULL; }
            buf = grown;
        }
    }
    buf[len] = 0;
    *out_len = len;
    return buf;
}

int main(int argc, char **argv) {
    if (argc != 3)
        return fail("usage: easyremote-forward <socket> <fn>  (args on stdin)");
    const char *path = argv[1], *fn = argv[2];

    size_t in_len = 0;
    char *in = read_all(stdin, &in_len);
    if (!in) return fail("out of memory");
    while (in_len && (unsigned char)in[in_len - 1] <= ' ') in[--in_len] = 0;
    const char *args = in_len ? in : "{}";

    int sock = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sock < 0) return fail("socket() failed");
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof addr);
    addr.sun_family = AF_UNIX;
    if (strlen(path) >= sizeof addr.sun_path) return fail("socket path too long");
    strcpy(addr.sun_path, path);
    if (connect(sock, (struct sockaddr *)&addr, sizeof addr) != 0) {
        fprintf(stderr,
                "easyremote host unreachable at %s — is the ComputeNode process"
                " running?\n", path);
        return 1;
    }

    /* fn names are validated upstream to [A-Za-z0-9_.-]: no escaping needed. */
    size_t req_cap = strlen(fn) + strlen(args) + 32;
    char *req = malloc(req_cap);
    if (!req) return fail("out of memory");
    int req_len = snprintf(req, req_cap, "{\"fn\":\"%s\",\"args\":%s}\n", fn, args);
    if (send(sock, req, (size_t)req_len, 0) != req_len) return fail("send failed");

    size_t cap = 1 << 16, len = 0;
    char *resp = malloc(cap);
    if (!resp) return fail("out of memory");
    ssize_t got;
    while ((got = recv(sock, resp + len, cap - len - 1, 0)) > 0) {
        len += (size_t)got;
        if (resp[len - 1] == '\n') break;
        if (len + 1 >= cap) {
            char *grown = realloc(resp, cap *= 2);
            if (!grown) return fail("out of memory");
            resp = grown;
        }
    }
    while (len && (resp[len - 1] == '\n' || resp[len - 1] == '\r')) len--;
    resp[len] = 0;

    static const char OK[] = "{\"ok\":true,\"result\":";
    static const char ERR[] = "{\"ok\":false,\"error\":";
    if (len > sizeof OK - 1 && memcmp(resp, OK, sizeof OK - 1) == 0) {
        fwrite(resp + sizeof OK - 1, 1, len - (sizeof OK - 1) - 1, stdout);
        return 0;
    }
    if (len > sizeof ERR - 1 && memcmp(resp, ERR, sizeof ERR - 1) == 0) {
        fprintf(stderr, "%.*s\n", (int)(len - (sizeof ERR - 1) - 1),
                resp + sizeof ERR - 1);
        return 1;
    }
    return fail("easyremote host sent an unrecognized response");
}
