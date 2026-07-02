#######################################################################
# File:             client.py
# Author:           George Freedland
# Purpose:          CSC645 Assigment #1 TCP socket programming
# Description:      Template client class.
# Running:          Python 2: python client.py
#                   Python 3: python3 client.py
#
########################################################################
import socket
import struct
import pickle

# Constants:
HEADER = 4096


class Client(object):
    """
    The client class provides the following functionality:
    1. Connects to a TCP server
    2. Send serialized data to the server by requests
    3. Retrieves and deserialize data from a TCP server
    """

    def __init__(self):
        """
        Class constructor
        """
        # Creates the client socket and empty data fields to send server.
        # AF_INET refers to the address family ipv4.
        # The SOCK_STREAM means connection oriented TCP protocol.
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
        self.messageToRecipient = ''
        self.recipient = ''
        self.roomId = ''
        self.chatMessage = ''

    # Returns the client id.
    def getClientId(self):
        return self.clientId

    def connect(self):
        """
        TODO: Connects to a server. Implements exception handler if connection is resetted.
            Then retrieves the client id assigned from server, and sets
        :param host:
        :param port:
        :return: VOID
        """
        try:
            self.clientSocket.connect((self.hostIp, self.hostPort))
        except socket.error:
            print('Error Connecting To Server.')
            self.clientSocket.close()
            return

        print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        print(
            f'Successfully connected to server: {self.hostIp}/{self.hostPort}')

        # Sets the client id by recieving it automatically after connecting
        self.setClientId()
        # Sets up the data and sends the client name to server.
        self.sendClientName()
        # Waits for server ok
        self.waitForOk()
        # Asks for content
        self.requestContent()

        # client is put in listening mode to retrieve data from server.
        # and loop while still getting a response or client exit.
        while True:
            data = self.receive()
            if not data:
                print('No data being received')
                break

            request = {
                "header": HEADER,
                "type": None,
                "content": None
            }

            # Displays the content and checks the infoNeeded dictionary
            # for more value/question pairs
            if(data['type'] == "NEEDMORE"):
                if data['content'] is None:
                    pass
                else:
                    print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                    print(f"{data['content']}")
                    print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

                # Gets the options and sets the dictionary request up
                infoNeeded = data.get('infoNeeded') or {}
                for key, value in infoNeeded.items():
                    if value[0] == "int":
                        correct = False
                        while correct == False:
                            theInput = input(value[1])
                            try:
                                request[key] = int(theInput)
                                correct = True
                            except:
                                print('You must enter an integer.')
                    else:
                        correct = False
                        theInput = ''
                        while correct == False:
                            theInput = input(value[1])
                            if len(theInput) != 0:
                                correct = True
                            else:
                                print('You must enter a string.')

                        request[key] = theInput

                # Tells server it's a menu selection.
                request['type'] = "MENUOPTION"
                self.send(request)  # Sends request

            elif(data['type'] == "DONE"):
                print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                print(f"{data['content']}")
                print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                request['header'] = HEADER
                request['type'] = "GET"
                request['content'] = "MENU"
                self.send(request)  # Sends request

            # elif(data['messageCode'] == "NEWCHAT"):
            #     print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
            #     print(f"content from server: \n{content}")
            #     print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n")
            #     # print('Client Fetching menu again...')
            #     data['header'] = HEADER
            #     # data['selected_menu_option'] = selected_menu_option
            #     data['messageType'] = "FETCH"
            #     data['content'] = self.clientName
            #     self.send(data)  # Sends request

            # Server acknowledge the client has exited.
            elif(data['type'] == "EXIT"):
                print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                print('Client Exitting...')
                print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                break

        self.close()  # closes client after loop breaks

    def setClientId(self):
        """
        Sets the client id assigned by the server to this client 
        after a succesfull connection.
        :return:
        """
        while True:
            data = self.receive()  # deserialized data
            if data is None:
                print('Lost connection to server during handshake.')
                break
            # extracts and sets the client id to this client
            if data['type'] == "HELLO":
                self.clientId = data['content']
                print("Client id: " + str(self.clientId) +
                      " \nClient User Name: " + str(self.clientName))
                print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                break
            elif data['type'] == "NO":
                print("Server is currently full you are put in a queue.")
                print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

    def sendClientName(self):
        # Set the setName data request to send to server after getting ID
        # Data should have a header (to show size of content)
        # a type: HELLO, and content will be the name of the client.
        request = {
            'header': HEADER,
            'type': "HELLO",
            'content': self.clientName
        }

        # Automatically send the first "HELLO" data request to the server to get a clientId back.
        # Server will send back an OK or NO data request
        try:
            self.send(request)
        except socket.error:
            print('Error sending data, no point of waiting for response')
            self.clientSocket.close()
            return

    # If the server message type is OK then we break loop and continue.
    def waitForOk(self):
        while True:
            data = self.receive()  # deserialized data
            if data is None:
                print('Lost connection to server while waiting for acknowledgement.')
                break
            if data['type'] == "OK":
                break
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
            return

    def send(self, data):
        """
        Serializes and then sends data to the server using a 4-byte
        big-endian length prefix so the server can read exactly one message.
        :param data:
        :return:
        """
        payload = pickle.dumps(data)  # serialized data
        try:
            self.clientSocket.sendall(struct.pack('>I', len(payload)) + payload)
        except socket.error:
            print('Error with socket send.')
            return

    def _recv_all(self, n):
        """
        Reads exactly n bytes from the socket, or returns None if the server
        closes the connection before n bytes arrive.
        """
        buffer = bytearray()
        while len(buffer) < n:
            try:
                chunk = self.clientSocket.recv(n - len(buffer))
            except socket.error:
                print('Error receiving data.')
                return None
            if not chunk:
                return None
            buffer.extend(chunk)
        return bytes(buffer)

    def receive(self):
        """
        Reads one length-prefixed message and deserializes it with pickle.
        :return: the deserialized data, or None if the server disconnected.
        """
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
        """
        TODO: close the client socket
        :return: VOID
        """
        print('Client is closing.')
        self.clientSocket.close()

    # First function to run after constructor,
    # Fetches what ip/port and username the client wants to use.
    def getUserInput(self):
        self.hostIp = input("Enter the server IP Address: ")
        self.hostPort = int(input("Enter the server port: "))
        self.clientName = input("Your id key (i.e your name): ")


if __name__ == '__main__':
    client = Client()
    client.getUserInput()
    client.connect()
