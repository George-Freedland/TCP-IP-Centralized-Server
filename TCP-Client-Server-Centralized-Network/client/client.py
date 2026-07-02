#######################################################################
# File:             client.py
# Author:           George Freedland
# Purpose:          CSC645 Assigment #1 TCP socket programming
# Description:      TCP chat/messaging client.
# Running:          python3 client.py
########################################################################
import sys
import socket
import struct
import pickle
import queue
import threading

# readline lets a background thread redraw a half-typed line when an
# incoming message interrupts the prompt. It's part of the standard library
# on macOS/Linux; on platforms without it we degrade gracefully.
try:
    import readline  # noqa: F401
    _HAS_READLINE = True
except ImportError:
    _HAS_READLINE = False

# Constants:
HEADER = 4096
CONNECT_TIMEOUT = 30  # seconds to wait before giving up on a connection


class Client(object):
    """
    The client class provides the following functionality:
    1. Connects to a TCP server
    2. Send serialized data to the server by requests
    3. Retrieves and deserialize data from a TCP server
    4. Displays real-time messages (broadcasts, direct messages, chat rooms)
       pushed by the server, interrupting the current prompt and restoring it.
    """

    def __init__(self):
        """
        Class constructor
        """
        try:
            self.clientSocket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
        except socket.error:
            print('Error creating socket')

        # Initialize all variables of client we will send to server.
        self.clientId = 0
        self.clientName = ''
        self.hostIp = ''
        self.hostPort = ''

        # Concurrency plumbing:
        # - responseQueue carries request/response messages from the receiver
        #   thread to the main thread.
        # - _io_lock serializes all writes to the terminal.
        self.responseQueue = queue.Queue()
        self._io_lock = threading.Lock()
        self._running = False
        self._at_prompt = False
        self._current_prompt = ''
        self._receiver_thread = None

    # Returns the client id.
    def getClientId(self):
        return self.clientId

    def connect(self):
        """
        Connects to the server with a bounded timeout, performs the handshake,
        then starts the background receiver thread and the menu loop.
        :return: VOID
        """
        # Bound the connect + handshake so a wrong IP/port can't hang forever.
        self.clientSocket.settimeout(CONNECT_TIMEOUT)
        try:
            self.clientSocket.connect((self.hostIp, self.hostPort))
        except socket.timeout:
            print(f"\nConnection timed out after {CONNECT_TIMEOUT} seconds. "
                  "Check the server IP/port and make sure the server is running.")
            self.clientSocket.close()
            return
        except ConnectionRefusedError:
            print("\nConnection refused: nothing is listening on that port. "
                  "Check the port number and that the server is running.")
            self.clientSocket.close()
            return
        except socket.gaierror:
            print("\nInvalid server address. Check the IP address / hostname you entered.")
            self.clientSocket.close()
            return
        except (OverflowError, socket.error) as e:
            print(f"\nCould not connect to the server: {e}")
            self.clientSocket.close()
            return

        print(f'Successfully connected to server: {self.hostIp}/{self.hostPort}')

        # Handshake (still bounded by the connect timeout).
        try:
            if not self.setClientId():
                self.clientSocket.close()
                return
            self.sendClientName()
            if not self.waitForOk():
                self.clientSocket.close()
                return
        except socket.timeout:
            print(f"\nThe server did not respond during the handshake "
                  f"(timed out after {CONNECT_TIMEOUT} seconds).")
            self.clientSocket.close()
            return

        # Handshake done: switch to blocking mode for normal operation.
        self.clientSocket.settimeout(None)

        # Start the background receiver and run the interactive menu loop.
        self._running = True
        self._receiver_thread = threading.Thread(
            target=self._receiver_loop, daemon=True)
        self._receiver_thread.start()

        self.requestContent()  # ask for the menu
        self._menu_loop()
        self.close()

    # ------------------------------------------------------------------
    # Terminal helpers
    # ------------------------------------------------------------------
    def _say(self, text):
        """Thread-safe print used by the main thread."""
        with self._io_lock:
            print(text)

    def _emit(self, text):
        """Prints a message that arrived asynchronously. If the user is
        currently at a prompt, the line is cleared, the message is printed,
        and the prompt (plus anything already typed) is restored below it."""
        with self._io_lock:
            line_buffer = readline.get_line_buffer() if (
                _HAS_READLINE and self._at_prompt) else ''
            # \r returns to column 0, \033[2K clears the whole line.
            sys.stdout.write('\r\033[2K')
            sys.stdout.write(text + '\n')
            if self._at_prompt:
                sys.stdout.write(self._current_prompt + line_buffer)
            sys.stdout.flush()

    def _input(self, prompt):
        """input() wrapper that records the active prompt so the receiver
        thread can restore it after printing an incoming message."""
        with self._io_lock:
            self._current_prompt = prompt
            self._at_prompt = True
        try:
            return input(prompt)
        finally:
            with self._io_lock:
                self._at_prompt = False
                self._current_prompt = ''

    # ------------------------------------------------------------------
    # Background receiver
    # ------------------------------------------------------------------
    def _receiver_loop(self):
        """Continuously reads messages from the socket. Asynchronous PUSH
        messages are printed immediately; everything else is a response to a
        request and is handed to the main thread through the queue."""
        while self._running:
            data = self.receive()
            if data is None:
                # Server closed the connection: unblock the main thread.
                self.responseQueue.put(None)
                break
            if data.get('type') == "PUSH":
                self._emit(data['content'])
            else:
                self.responseQueue.put(data)

    def _menu_loop(self):
        """Main thread loop: consumes server responses and drives the UI."""
        while self._running:
            data = self.responseQueue.get()

            # Sentinel from the receiver thread: connection lost.
            if data is None:
                self._say('\nDisconnected from server.')
                break

            msg_type = data.get('type')

            if msg_type == "NEEDMORE":
                self._handle_needmore(data)
            elif msg_type == "DONE":
                if data['content'] is not None:
                    self._say(f"\n{data['content']}\n")
                self.requestContent()  # go back to the menu
            elif msg_type == "CHATSTART":
                self._say(f"\n{data['content']}\n")
                self._chat_session()
                self.requestContent()  # back to the menu after leaving
            elif msg_type == "EXIT":
                self._say('\nClient exiting...')
                self._running = False
                break

    def _handle_needmore(self, data):
        """Prints any content, collects the requested fields from the user,
        and sends them back as a MENUOPTION message."""
        if data['content'] is not None:
            self._say(f"\n{data['content']}")

        request = {"header": HEADER, "type": None, "content": None}
        infoNeeded = data.get('infoNeeded') or {}
        for key, value in infoNeeded.items():
            if value[0] == "int":
                while True:
                    theInput = self._input(value[1])
                    try:
                        request[key] = int(theInput)
                        break
                    except ValueError:
                        self._say('You must enter an integer.')
            else:
                while True:
                    theInput = self._input(value[1])
                    if len(theInput) != 0:
                        request[key] = theInput
                        break
                    self._say('You must enter a value.')

        request['type'] = "MENUOPTION"
        self.send(request)

    def _chat_session(self):
        """Interactive chat loop. Incoming messages from other members are
        printed in real time by the receiver thread; this loop only reads and
        sends the local user's lines until they leave."""
        while self._running:
            line = self._input(f"{self.clientName}> ")
            self.send({'header': HEADER, 'type': "CHATLINE", 'content': line})
            if line.strip().lower() in ('exit', 'bye'):
                self._say('Leaving chat room...')
                break

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------
    def setClientId(self):
        """
        Sets the client id assigned by the server after a successful
        connection. Returns True on success, False if the connection dropped.
        """
        while True:
            data = self.receive()  # deserialized data
            if data is None:
                print('Lost connection to server during handshake.')
                return False
            if data['type'] == "HELLO":
                self.clientId = data['content']
                print("Client id: " + str(self.clientId) +
                      "\nClient User Name: " + str(self.clientName))
                return True
            elif data['type'] == "NO":
                print("Server is currently full. Please try again later.")
                return False

    def sendClientName(self):
        request = {
            'header': HEADER,
            'type': "HELLO",
            'content': self.clientName
        }
        try:
            self.send(request)
        except socket.error:
            print('Error sending data, no point of waiting for response')
            self.clientSocket.close()

    def waitForOk(self):
        """Returns True once the server acknowledges, False if the connection
        dropped."""
        while True:
            data = self.receive()  # deserialized data
            if data is None:
                print('Lost connection to server while waiting for acknowledgement.')
                return False
            if data['type'] == "OK":
                return True
            elif data['type'] == "NACK":
                print("Server is having issues.")

    # Simple GET request for the menu
    def requestContent(self):
        request = {
            'header': HEADER,
            'type': "GET",
            'content': "MENU"
        }
        try:
            self.send(request)
        except socket.error:
            print('Error sending data, no point of waiting for response')
            self.clientSocket.close()

    # ------------------------------------------------------------------
    # Wire protocol (length-prefixed pickle)
    # ------------------------------------------------------------------
    def send(self, data):
        """
        Serializes and sends data to the server using a 4-byte big-endian
        length prefix so the server can read exactly one message.
        """
        payload = pickle.dumps(data)  # serialized data
        try:
            self.clientSocket.sendall(struct.pack('>I', len(payload)) + payload)
        except socket.error:
            print('Error with socket send.')

    def _recv_all(self, n):
        """Reads exactly n bytes, or returns None if the server closes the
        connection. socket.timeout is allowed to propagate (used only during
        the bounded handshake)."""
        buffer = bytearray()
        while len(buffer) < n:
            try:
                chunk = self.clientSocket.recv(n - len(buffer))
            except socket.timeout:
                raise
            except socket.error:
                return None
            if not chunk:
                return None
            buffer.extend(chunk)
        return bytes(buffer)

    def receive(self):
        """Reads one length-prefixed message; returns None on disconnect."""
        raw_length = self._recv_all(4)
        if raw_length is None:
            return None
        message_length = struct.unpack('>I', raw_length)[0]
        raw_data = self._recv_all(message_length)
        if raw_data is None:
            return None
        try:
            return pickle.loads(raw_data)
        except pickle.UnpicklingError:
            print('Error deserializing data from server.')
            return None

    def close(self):
        """Closes the client socket."""
        self._running = False
        print('Client is closing.')
        try:
            self.clientSocket.close()
        except socket.error:
            pass

    # First function to run after constructor,
    # Fetches what ip/port and username the client wants to use.
    def getUserInput(self):
        self.hostIp = input("Enter the server IP Address: ").strip()
        while True:
            try:
                self.hostPort = int(input("Enter the server port: ").strip())
                break
            except ValueError:
                print("The port must be a number (e.g. 12000).")
        self.clientName = input("Your id key (i.e your name): ").strip()


if __name__ == '__main__':
    client = Client()
    client.getUserInput()
    client.connect()
