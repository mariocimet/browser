import socket
import ssl

def addHeaders(request, headers):
    for key, val in headers.items():
        request += f'\r\n{key}: {val}'
    return request + '\r\n\r\n'
    

def request(url):
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
    scheme, url = url.split("://", 1)
    assert scheme in ["http", "https", "file"], \
    "Unknown scheme {}".format(scheme)
    host, path = url.split("/", 1)


    if ":" in host:
      host, port = host.split(":", 1)
      port = int(port)
    
    path = "/" + path
    port = 80 if scheme == "http" else 443

    # wrap the socket with a ssl context if we're using https
    if scheme == "https":
      ctx = ssl.create_default_context()
      s = ctx.wrap_socket(s, server_hostname=host)
    
    s.connect((host, port))

    request = f'GET {path} HTTP/1.1'
    headers = {"Host":host, "Connection":"close", "User-Agent":"mcdat"}
    requestWithHeaders = addHeaders(request, headers)
    
    print(requestWithHeaders)

    # need to send the data in binary, which means encoding: https://www.python.org/dev/peps/pep-0498/#no-binary-f-strings
    s.send(requestWithHeaders.encode("latin-1"))

    # socket.makefile returns the whole response associated with the socket (otherwise we'd need to loop over the response to parse it)
    response = s.makefile("r", encoding="latin-1", newline="\r\n")
    statusline = response.readline()
    version, status, explanation = statusline.split(" ", 2)

    # assert OK status, throw an error for non 200 return codes (300s for redirects, 400 for client errors, 500 for server errors etc.)
    assert status == "200", "{}: {}".format(status, explanation)
    # Parse headers
    headers = {}
    while True:
        line = response.readline()
        if line == "\r\n": break
        header, value = line.split(":", 1)
        headers[header.lower()] = value.strip()

    body = response.read()
    s.close()
    return headers, body

# Initial parser state machine to print just text, not tags, from an html page.
def show(body):
    in_angle = False
    for c in body:
        if c == "<":
            in_angle = True
        elif c == ">":
            in_angle = False
        elif not in_angle:
            print(c, end="")

def load(url):
    headers, body = request(url)
    show(body)


if __name__ == "__main__":
    import sys
    load(sys.argv[1])