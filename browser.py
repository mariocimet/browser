import socket
import ssl
import gzip
import pdb

URL_SCHEMES = ["http", "https", "file", "data", "view-source"]
SUPPORTED_ENTITIES = {"&lt;": "<", "&gt;": ">"}

def add_headers(request, headers):
    for key, val in headers.items():
        request += f"\r\n{key}: {val}"
    return request + "\r\n\r\n"


def print_entity(entity):
    if entity in SUPPORTED_ENTITIES:
        print(SUPPORTED_ENTITIES.get(entity), end="")


def transform(source_code):
    for entity, reserved_char in SUPPORTED_ENTITIES.items():
        source_code = source_code.replace(reserved_char, entity)
    return f"<body>{source_code}</body>"

    

def request(url):
    if not url:
        return {}, open("/home/mario/browser/browser.py", "r")

    # Use socket to connect to the host, implementation of https://en.wikipedia.org/wiki/Berkeley_sockets
    # AF = Address family, because it's a web browser we use INET6 instead of, say UNIX or BLUETOOTH.
    # Note: INET6 is compatible w/ IPv6 and backwards-compatible w/ IPv4
    # STREAM=Streaming, allows arbitrary data to be sent in a, well, stream. Common alternative is SOCK_DGRAM which requires packets of a specific size
    # RAW, RDM, and SEQPACKET are also allowed but are very rare.
    # IPPROTO = which protocol to use, TCP is the most common (the handshakey one). Alternatives include UDP or Google's implementation of it, QUIC
    # These are all defaults so this block is the equivalent of calling socket.socket()
    s = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    # Split the URL into parts
    # Scheme, describes how to retrieve the resource
    # Host and path describe where to get it and what to get from it
    # Port specifies the connection interface to use
    scheme, url = url.split(":", 1)

    assert scheme in URL_SCHEMES, "Unknown scheme {}".format(scheme)

    if scheme == "view-source":
        subscheme, url = url.split(":")

    if scheme != "data":
        prefix, url = url.split("//", 1)

    host, path = url.split("/", 1)

    if ":" in host:
        host, port = host.split(":", 1)
        port = int(port)

    path = "/" + path
    port = 80 if scheme == "http" else 443

    # wrap the socket with a ssl context if we're using https
    if scheme or subscheme == "https":
        ctx = ssl.create_default_context()
        s = ctx.wrap_socket(s, server_hostname=host)

    if scheme == "file":
        return {}, open(url, "r")

    if scheme == "data":
        encoding, content = path.split(",", 1)
        return {}, content

    s.connect((host, port))

    request = f"GET {path} HTTP/1.1"
    headers = {
        "Host": host,
        "Connection": "close",
        "User-Agent": "mcdat",
        "Accept-Encoding": "gzip",
    }
    requestWithHeaders = add_headers(request, headers)

    # need to send the data in binary, which means encoding: https://www.python.org/dev/peps/pep-0498/#no-binary-f-strings
    s.send(requestWithHeaders.encode("utf-8"))

    # socket.makefile returns the whole response associated with the socket (otherwise we'd need to loop over the response to parse it)
    response = s.makefile("b", newline="\r\n")

    statusline = response.readline().decode("utf-8")
    version, status, explanation = statusline.split(" ", 2)

    # assert OK status, throw an error for non 200 return codes (300s for redirects, 400 for client errors, 500 for server errors etc.)
    assert status == "200", "{}: {}".format(status, explanation)
    # Parse headers

    headers = {}
    while True:
        line = response.readline().decode("utf-8")
        if line == "\r\n":
            break
        header, value = line.split(":", 1)
        headers[header.lower()] = value.strip()

    if "transfer-encoding" in headers and headers["transfer-encoding"] == "chunked":
        lines = response.read().split(b'\r\n')
        pdb.set_trace()
        body = ''
        for index, line in enumerate(lines):
            if index % 2 == 0:
                continue
            else:
                body += gzip.decompress(line).decode("utf-8")

    if headers["content-encoding"] != "gzip":
        body = response.read().decode("utf-8")

    # if headers["transfer-encoding"] == "chunked":
    #     pdb.set_trace()

    # body = gzip.decompress(response.read()).decode("utf-8")

    s.close()

    if scheme == "view-source":
        body = transform(body)

    return headers, body


# Initial parser state machine to print just text, not tags, from an html page.
def show(source_text):
    in_angle = False
    in_body = False
    tag = ""
    in_entity = False
    entity = ""

    for c in source_text:
        if c == "<":
            in_angle = True
            continue
        elif c == ">":
            in_angle = False
            if tag == "body":
                in_body = True
            elif tag == "/body":
                in_body = False
            tag = ""
            continue
        elif in_angle:
            tag += c
            continue

        if not in_body:
            continue

        if c == "&":
            in_entity = True
            entity += c
            continue
        elif in_entity and c == ";":
            in_entity = False
            entity += c
            print_entity(entity)
            entity = ""
            continue
        elif in_entity:
            entity += c
        if not in_entity:
            print(c, end="")


def load(url):
    headers, body = request(url)
    show(body)


if __name__ == "__main__":
    import sys

    if len(sys.argv) == 1:
        load("")
    elif len(sys.argv) == 2:
        load(sys.argv[1])
    else:
        raise Exception(f"Too many arguments. Expected 1, given {len(sys.argv) -1}")
