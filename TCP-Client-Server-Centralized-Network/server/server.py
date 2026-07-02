#######################################################################
# File:             server.py
# Author:           George Freedland
# Purpose:          CSC645 Assigment #1 TCP socket programming
# Description:      Multithreaded TCP chat/messaging server.
# Running:          python3 server.py
#                   Note: Must run the server before the client.
########################################################################

import socket
import struct
import logging
import pickle
from threading import Thread, Lock, active_count
from client_handler import ClientHandler

# Timestamped, single-line logging so the server console is easy to scan.
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('server')

PORT = 12000
# Bind to all interfaces so the server is reachable via 127.0.0.1 and the
# machine's LAN IP when testing locally.
BIND_HOST = "0.0.0.0"


def _get_lan_ip():
    """Best-effort LAN IP for display only. Falls back to 127.0.0.1 on
    machines where the hostname does not resolve."""
    try:
        return socket.gethostbyname(socket.gethostname())
    except socket.error:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except socket.error:
            return "127.0.0.1"


# The LAN IP is only used for display so clients know where to connect.
SERVER = _get_lan_ip()
ADDR = (BIND_HOST, PORT)
HEADER = 4096


class Server(object):

    MAX_NUM_CONN = 10  # keeps 10 clients in queue
    DISCONNECT_OPTION = 7  # menu option that closes a client's session

    # GENERAL SERVER INITIALIZATION - init local variables, create and bind socket.
    def __init__(self, ip_address=BIND_HOST, port=PORT):
        self.host = ip_address
        self.port = port
        self.numOfClients = 0
        self.connected = True
        # dictionary of client connections. format {clientid: connobject}
        self.clientHandlerObjects = {}
        # dictionary of client names. format {clientid: clientName}
        self.clientNames = {}
        # store-and-forward mailbox for direct messages
        self.unreadMessages = []
        # Dictionary that holds open chatRooms.
        self.chatRooms = {}
        # One lock per connection so that pushes coming from other client
        # threads never interleave (and corrupt the framing) with the writes
        # made by a connection's own thread. format {conn: Lock}
        self._locks = {}

        # create an INET, STREAMing socket
        try:
            self.serversocket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            # Allow quick restarts without hitting "address already in use".
            self.serversocket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except socket.error:
            log.error('Error creating socket.')

        # bind the socket to a public host, and a well-known port
        try:
            self.serversocket.bind((ip_address, port))
        except socket.error:
            log.error('Error binding server to ip and port')
            self.serversocket.close()

    def register_connection(self, conn):
        """Create a dedicated send lock for a newly accepted connection."""
        self._locks[conn] = Lock()

    # Thread Starts
    def threaded_handle_client(self, conn, addr):
        # On init this sets up variables in ClientHandler.
        # Also sends ID, gets Name then sends Ok
        client_handler = ClientHandler(self, conn, addr)
        log.info(f"New connection established from {addr[0]}:{addr[1]}")
        log.info(f"Active connections: {active_count() - 1}")

        # Main receive loop determines what to do based on the 'type'
        while self.connected:
            try:
                message = self.receive(conn)
            except (socket.error, EOFError, pickle.UnpicklingError):
                message = None

            # A None message means the client closed the connection.
            if message is None:
                self.numOfClients -= 1
                log.info(
                    f"{self.clientNames.get(addr[1], addr[1])} disconnected from the server")
                break

            log.info(
                f"Message from {self.clientNames.get(addr[1], addr[1])} "
                f"({addr[1]}): type={message['type']}")

            # Handle get menu request
            if message['type'] == "GET" and message['content'] == "MENU":
                log.info(f"Sending menu to {addr[1]}")
                client_handler._sendMenu()

            # Handle menu option select
            if message['type'] == "MENUOPTION":
                log.info(
                    f"Handling option {message['menuOption']} for {addr[1]}")
                client_handler.process_options(message)
                if message['menuOption'] == self.DISCONNECT_OPTION:
                    self.numOfClients -= 1
                    break

        # Runs clear/close on client connection (guarded so an abrupt
        # disconnect can't raise KeyError during cleanup).
        self.clientNames.pop(addr[1], None)
        conn_to_close = self.clientHandlerObjects.pop(addr[1], None)
        self._locks.pop(conn, None)
        if conn_to_close is not None:
            try:
                conn_to_close.close()
            except socket.error:
                pass

    # Listens to new clients and sets max clients to MAX_NUM_CONN
    def _listen(self):
        try:
            self.serversocket.listen(self.MAX_NUM_CONN)
            log.info(f"Listening at {SERVER}:{self.port}")
        except socket.error:
            log.error('Error binding server to ip and port')
            self.serversocket.close()

    # Runs a loop running serversocket.accept to fetch client info and assign a thread to it.
    def _accept_clients(self):
        while True:
            try:
                conn, addr = self.serversocket.accept()
                self.numOfClients += 1
                if self.numOfClients <= self.MAX_NUM_CONN:
                    Thread(target=self.threaded_handle_client, args=(
                        conn, addr), daemon=True).start()
                else:
                    self.register_connection(conn)
                    response = {
                        'header': HEADER,
                        'type': "NO",
                        'content': None
                    }
                    self.numOfClients -= 1
                    log.warning(
                        "A client tried to connect but the server is full.")
                    self.send(conn, response)
                    self._locks.pop(conn, None)
            except socket.error:
                log.error('Error establishing connection with client')
                break

    # Serializes a dictionary with pickle and sends it to the client using a
    # 4-byte big-endian length prefix so the receiver knows exactly how many
    # bytes make up one message. This prevents messages from being split or
    # merged on the TCP stream. The per-connection lock guarantees that two
    # threads never write a half message to the same socket at once.
    def send(self, conn, data):
        serializedData = pickle.dumps(data)
        framed = struct.pack('>I', len(serializedData)) + serializedData
        lock = self._locks.get(conn)
        if lock is not None:
            with lock:
                conn.sendall(framed)
        else:
            conn.sendall(framed)

    # Reads exactly n bytes from the socket, or returns None if the peer
    # closes the connection before n bytes arrive.
    def _recv_all(self, conn, n):
        buffer = bytearray()
        while len(buffer) < n:
            chunk = conn.recv(n - len(buffer))
            if not chunk:
                return None
            buffer.extend(chunk)
        return bytes(buffer)

    # Receives one length-prefixed message and deserializes it with pickle.
    # Returns None when the client has disconnected.
    def receive(self, conn):
        raw_length = self._recv_all(conn, 4)
        if raw_length is None:
            return None
        message_length = struct.unpack('>I', raw_length)[0]
        raw_data = self._recv_all(conn, message_length)
        if raw_data is None:
            return None
        return pickle.loads(raw_data)

    # Sends the client id and waits for a HELLO name send.
    def sendClientId(self, conn, id):
        request = {
            'header': HEADER,
            'type': "HELLO",
            'content': id
        }
        self.send(conn, request)

    # Recieves the client's Name
    def receiveClientName(self, conn, id):
        data = self.receive(conn)
        if data is not None and data['type'] == "HELLO":
            self.clientNames[id] = data['content']

    # Send ok to client
    def sendOk(self, conn):
        request = {
            'header': HEADER,
            'type': "OK",
            'content': None
        }
        self.send(conn, request)

    # Main driver after init
    def run(self):
        self._listen()
        self._accept_clients()


# File starts here.
if __name__ == '__main__':
    log.info('Server is starting....')
    log.info(
        f'Clients on this machine can connect using IP 127.0.0.1 and port {PORT}')
    log.info(
        f'Clients on your LAN can connect using IP {SERVER} and port {PORT}')
    server = Server()
    server.run()
