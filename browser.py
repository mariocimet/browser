import socket


# Use socket to connect to the host, implementation of https://en.wikipedia.org/wiki/Berkeley_sockets
    # These are all defaults so this block is the equivalent of calling socket.socket()
    # AF = Address family, because it's a web browser we use INET6 instead of, say UNIX or BLUETOOTH.
    # Note: INET6 is compatible w/ IPv6 and backwards-compatible w/ IPv4
    # STREAM=Streaming, allows arbitrary data to be sent in a, well, stream. Common alternative is SOCK_DGRAM which requires packets of a specific size
    # RAW, RDM, and SEQPACKET are also allowed but are very rare.
    # IPPROTO = which protocol to use, TCP is the most common (the handshakey one). Alternatives include UDP or Google's implementation of it, QUIC 

s = socket.socket(
    family=socket.AF_INET,
    type=socket.SOCK_STREAM,
    proto=socket.IPPROTO_TCP,
)
def request(url):
    #Split the URL into parts 

    #Scheme, aka *how to get the info*
    assert url.startswith("http://")
    url = url[len("http://"):]
    # Host and path describe where to get and what to get
    host, path = url.split("/", 1)
    path = "/" + path

    s.connect((host, 80))

    # build request string
    # want to use string interpolation for path and host, but you need to send the data in binary
    # and you can't use binary f-strings, see: https://www.python.org/dev/peps/pep-0498/#no-binary-f-strings

    #send request
    s.send((f'GET {path} HTTP/1.0\r\n' + f'Host: {host}\r\n\r\n').encode())

    # socket.makefile returns the whole response associated with the socket (otherwise we'd need to loop over the response to parse it)
    response = s.makefile("r", encoding="utf8", newline="\r\n")
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
# Two states: in_angle and not, transitions to in_angle with "<" and to not with ">"
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