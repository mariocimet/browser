import socket
import ssl
import gzip
import pdb
from datetime import datetime, timedelta
import json
import redis
import re
import tkinter

r = redis.Redis()
WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
MAX_REDIRECTS = 20
URL_SCHEMES = ["http", "https", "file", "data", "view-source"]
SUPPORTED_ENTITIES = {"&lt;": "<", "&gt;": ">", "&amp;":"&"}

class Browser:
    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window, 
            width=WIDTH,
            height=HEIGHT
        )
        self.canvas.pack()
        self.scroll = 0
        self.window.bind("<Down>", self.scrolldown)  
        self.window.bind("<Up>", self.scrollup)

    def load(self, url):
        headers, body = request(url, 0)
        text = lex(body)
        self.display_list = layout(text)
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        for x, y, c in self.display_list:
            if y > self.scroll + HEIGHT: continue
            if y + VSTEP < self.scroll: continue
            self.canvas.create_text(x, y - self.scroll, text=c)

    def scrolldown(self, e):
        self.scroll += SCROLL_STEP
        self.draw()

    def scrollup(self, e):
        self.scroll -= SCROLL_STEP
        self.draw()

def add_headers(request, headers):
    for key, val in headers.items():
        request += f"\r\n{key}: {val}"
    return request + "\r\n\r\n"

def print_entity(entity):
    if entity in SUPPORTED_ENTITIES:
        return SUPPORTED_ENTITIES.get(entity)
    else:
        return entity

def transform(source_code):
    for entity, reserved_char in SUPPORTED_ENTITIES.items():
        source_code = source_code.replace(reserved_char, entity)
    return f"<body>{source_code}</body>"

def request(url, redirects):

    if not url:
        return {}, open("/home/mario/browser/browser.py", "r")

    if r.exists(url):
        headers = r.hget(url, 'headers')
        body = r.hget(url, 'body')
        return headers, body.decode("utf-8")

    if redirects > MAX_REDIRECTS:
        return {}, "Too many redirects"

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

    path_and_protocol = f"GET {path} HTTP/1.1"
    headers = {
        "Host": host,
        "Connection": "close",
        "User-Agent": "mcdat",
        "Accept-Encoding": "gzip",
    }
    requestWithHeaders = add_headers(path_and_protocol, headers)

    # need to send the data in binary, which means encoding: https://www.python.org/dev/peps/pep-0498/#no-binary-f-strings
    s.send(requestWithHeaders.encode("utf-8"))

    # socket.makefile returns the whole response associated with the socket (otherwise we'd need to loop over the response to parse it)
    response = s.makefile("b", newline="\r\n")

    statusline = response.readline().decode("utf-8")
    version, status, explanation = statusline.split(" ", 2)
    # Parse headers

    headers = {}
    while True:
        line = response.readline().decode("utf-8")
        if line == "\r\n":
            break
        header, value = line.split(":", 1)
        headers[header.lower()] = value.strip()
    
    # increment redirects to limit the amount of times we can be redirected and avoid loops
    if status == "301":
        if headers["location"][0] == "/":
            return request(f'{scheme}://{host}{path}')
        return request(headers["location"], redirects + 1)

    # assert OK status, throw an error for non 200 return codes (300s for redirects, 400 for client errors, 500 for server errors etc.)
    assert status == "200", "{}: {}".format(status, explanation)

    if "content-encoding" in headers and headers["content-encoding"] != "gzip":
        body = response.read().decode("utf-8")
    elif headers["content-encoding"] == gzip:
        body = gzip.decompress(response.read())

    # 'chunked' data must be processed, decompressed and recombined
    if "transfer-encoding" in headers and headers["transfer-encoding"] == "chunked":
        lines = response.read().split(b'\r\n')
        body = b''
        for index, line in enumerate(lines):
            if index % 2 == 0:
                continue
            else:
                body += line

        body = gzip.decompress(body).decode("utf-8")
    # if it's not chunked but still compressed, it must be decompressed
    elif headers["content-encoding"] == "gzip":
        body = gzip.decompress(response.read()).decode("utf-8")
    # if it's not compressed, can simply decode the bytes from the response.
    else:
        body = response.read().decode("utf-8")

    s.close()
    # when viewing source code, transform so that reserved characters are rendered as entities
    if scheme == "view-source":
        body = transform(body)

    # only cache if cache-control header gives us a max age.
    if "cache-control" in headers and re.match(r'max-age=[0-9]+', headers["cache-control"]):
        r.hset(f'{scheme}://{host}{path}', 'headers', json.dumps(headers))
        r.hset(f'{scheme}://{host}{path}', 'body', body)
        maxage = int(headers['cache-control'].split('=')[1])
        age = int(headers['age'])
        r.expire(f'{scheme}://{host}{path}', maxage - age)

    return headers, body

# Initial parser state machine to print just text, not tags, from an html page.
def lex(source_text):
    in_angle = False
    in_body = False
    tag = ""
    in_entity = False
    entity = ""
    text = ''

    for c in source_text:
        if c == "<":
            in_angle = True
            continue
        elif c == ">":
            in_angle = False
            if tag == "body" or tag.split(" ")[0] == "body":
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
            text += print_entity(entity)
            entity = ""
            continue
        elif in_entity:
            entity += c
        if not in_entity:
            text += c
    return text

#screen coordinates and page coordinates are different things
#layout is about page coordinates - where each character should live on a complete representation of a page
#rendering is about screen coordinates, how the page layout should be displayed to a user at a particular moment
#text -> display list, given vertical and horizontal step values defined in HSTEP and VSTEP
def layout(text):
    display_list = []
    cursor_x, cursor_y = HSTEP, VSTEP
    for c in text:
        display_list.append((cursor_x, cursor_y, c))
        if cursor_x >= WIDTH - HSTEP:
          cursor_y += VSTEP
          cursor_x = HSTEP
        else:
          cursor_x += HSTEP
    return display_list

if __name__ == "__main__":
    import sys

    if len(sys.argv) == 2:
        Browser().load(sys.argv[1])
        tkinter.mainloop()

    else:
        raise Exception(f"Wrong number of arguments. Expected 1, given {len(sys.argv) -1}")
