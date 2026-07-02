#######################################################################
# File:             client_handler.py
# Author:           George Freedland
# Purpose:          CSC645 Assigment #1 TCP socket programming
# Description:      Template ClientHandler class.
# Running:          Python 2: python server.py
#                   Python 3: python3 server.py
#                   Note: Must run the server before the client.
########################################################################
import pickle
import socket

HEADER = 4096  # header length


class ClientHandler(object):
    """
    The ClientHandler class provides methods to meet the functionality and services provided
    by a server. Examples of this are sending the menu options to the client when it connects,
    or processing the data sent by a specific client to the server.
    """

    def __init__(self, server_instance, conn, addr):
        """
        Class constructor already implemented for you
        :param server_instance: normally passed as self from server object
        :param conn: the socket representing the client accepted in server side
        :param addr: addr[0] = <server ip address> and addr[1] = <client id>
        """
        self.serverIp = addr[0]
        self.clientId = addr[1]
        self.server = server_instance
        self.conn = conn
        server_instance.clientHandlerObjects[addr[1]] = conn

        # Send the clientId to the client and receive the name back, then send an ok response.
        server_instance.sendClientId(conn, addr[1])
        server_instance.receiveClientName(conn, addr[1])
        server_instance.sendOk(conn)

        self.clientNames = server_instance.clientNames
        self.clientName = server_instance.clientNames[addr[1]]
        self.unreadMessages = server_instance.unreadMessages
        self.myRoomId = None

    def _sendMenu(self):
        """
        Sends the menu options to the client after the handshake between client and server is done.
        :return: VOID
        """
        # menu = Menu({'option 1': 'test1', 'option 2': 'test2'})
        # menu = Menu()
        infoNeeded = {
            'menuOption': ['int', 'Please enter a menu option: ']
        }

        data = {
            'header': HEADER,
            'type': "NEEDMORE",
            'content': "****** TCP Message App *******\nOptions Available: \n1. Get user list\n2. Send a message\n3. Get my messages\n4. Create a new chat room\n5. Join an existing chat room\n6. Broadcast a message to all users\n7. Disconnect from server",
            'infoNeeded': infoNeeded
        }
        self.server.send(self.conn, data)

    def process_options(self, data):
        """
        Process the option selected by the user and the data sent by the client related to that
        option. Note that validation of the option selected must be done in client and server.
        In this method, I already implemented the server validation of the option selected.
        :param data: the MENUOPTION message sent by this client.
        :return:
        """
        response = {
            'header': HEADER,
            'type': "NEEDMORE",
            'content': None,
            'infoNeeded': None
        }

        # validates a valid option selected and runs appropriate method.
        # Runs if-else on menuOption (value between 1-7 inclusive), prepares either a DONE (client will ask for menu)
        # or NEEDMORE with infoNeeded questions dictionary (key: question to get value)
        if 'menuOption' in data.keys() and 1 <= data['menuOption'] <= 7:
            option = data['menuOption']
            if option == 1:
                self._send_user_list()
            elif option == 2:
                infoNeeded = {
                    'recipientId': ["int", "Enter recipient's id: "],
                    'message': ["string", "Enter the message you want to send: "]
                }
                response['infoNeeded'] = infoNeeded
                self.server.send(self.conn, response)
                clientResponse = self.server.receive(self.conn)
                recipientId = clientResponse['recipientId']
                message = clientResponse['message']
                self._send_message(recipientId, message)
            elif option == 3:
                self._show_messages()
            elif option == 4:
                infoNeeded = {
                    'myRoomId': ["int", "Enter the room id you want to create(You only get one): "]
                }
                response['infoNeeded'] = infoNeeded
                self.server.send(self.conn, response)
                clientResponse = self.server.receive(self.conn)
                myRoomId = clientResponse['myRoomId']
                self._create_chat(myRoomId)
            elif option == 5:
                infoNeeded = {
                    'joinRoomId': ["int", "Enter the room id you want to join: "]
                }
                response['infoNeeded'] = infoNeeded
                self.server.send(self.conn, response)
                clientResponse = self.server.receive(self.conn)
                joinRoomId = clientResponse['joinRoomId']
                self._join_chat(joinRoomId)
            elif option == 6:
                infoNeeded = {
                    'broadcastMessage': ["string", "Enter the message to broadcast to all users: "]
                }
                response['infoNeeded'] = infoNeeded
                self.server.send(self.conn, response)
                clientResponse = self.server.receive(self.conn)
                self._broadcast_message(clientResponse['broadcastMessage'])
            elif option == 7:
                self._disconnect_from_server()
        else:
            print("The option selected is invalid")
            self._sendMenu()

    # When a DONE type is sent, the content is displayed. clientNames is updated at every login/logout.
    def _send_user_list(self):
        print('Sending user list')

        data = {
            'header': HEADER,
            'type': "DONE",
            'content': 'Users in the server: ' + str(self.clientNames)
        }
        self.server.send(self.conn, data)
        return None

    # If the recipient id is valid we send a message and confirm to the client the message to the id was send
    # Otherwise sends a "recipient not found" message to client so the client must select the sendmessage option again.
    def _send_message(self, recipientId, message):
        # Normalize to int so it matches the integer client ids used as keys
        # in clientNames and compared against in _show_messages.
        try:
            recipientId = int(recipientId)
        except (TypeError, ValueError):
            recipientId = None

        if (recipientId in self.clientNames.keys()):
            print("This recipient exists.")
            self.unreadMessages.append({
                'recipient': recipientId, 'messagecontent': message, 'sender': self.clientId, 'unread': True})
            data = {
                'header': HEADER,
                'type': "DONE",
                'content': 'Message Sent To: ' + str(recipientId) + '\nMessage: ' + message
            }
            self.server.send(self.conn, data)
        else:
            print("This recipient does NOT exist.")
            data = {
                'header': HEADER,
                'type': "DONE",
                'content': 'The recipient you entered does not exist'
            }
            self.server.send(self.conn, data)

    def _broadcast_message(self, message):
        """
        Sends a message from this client to every client currently connected
        to the server (including the sender, so they get confirmation).

        Each connected client is stored in server.clientHandlerObjects as
        {clientId: connectionSocket}. We iterate over a snapshot of that
        dictionary so that clients connecting/disconnecting mid-broadcast
        don't cause a "dictionary changed size during iteration" error.
        :param message: the text to broadcast.
        :return: VOID
        """
        broadcastContent = f"[BROADCAST] {self.clientName}: {message}"
        print(f"Broadcasting message from {self.clientName}: {message}")

        data = {
            'header': HEADER,
            'type': "DONE",
            'content': broadcastContent
        }

        for recipientId, conn in list(self.server.clientHandlerObjects.items()):
            try:
                self.server.send(conn, data)
            except (socket.error, OSError):
                # Skip clients that have already disconnected.
                print(f"Could not deliver broadcast to client {recipientId}.")

    def _show_messages(self):
        """
        TODO: send all the unreaded messages of this client. if non unread messages found, send an empty list.
        TODO: make sure to delete the messages from list once the client acknowledges that they were read.
        :return: VOID
        """
        messagesToShow = ''  # String to set.
        count = 0  # Count gets reset every time.

        for x in self.unreadMessages:
            # Display all unread messages pertaining to user, using a count variable to display amount of unread messages.
            if (x['recipient'] == self.clientId and x['unread'] == True):
                count += 1
                sender_name = self.clientNames.get(x['sender'], x['sender'])
                messagesToShow += ("Message: " +
                                   str(x['messagecontent']) + " From: " + str(sender_name) + "\n")
                x['unread'] = False

        messagesToShow = f"You have {count} unread messages\n" + \
            messagesToShow

        # Keep only messages that are still unread. Rebuilding the list in
        # place avoids mutating it while iterating (which skips elements).
        self.unreadMessages[:] = [
            m for m in self.unreadMessages if m['unread']]

        # Send Done request with content
        data = {
            'header': HEADER,
            'type': "DONE",
            'content': messagesToShow
        }
        self.server.send(self.conn, data)

    def _create_chat(self, myRoomId):
        """
        TODO: Creates a new chat in this server where two or more users can share messages in real time.
        :param room_id:
        :return: VOID
        """
        # Sets a clients personal room id and shows chat room created + instructions.
        self.myRoomId = myRoomId
        # Chatrooms Format: {'chatroomId(1234)': chatroomInfo = {'ownerId':50399,
        #                                                         usersInChat = {'userid':'username'},
        #                                                         messages = {'sendername': 'message'} },
        #                    'chatroomId(2235)':...}
        if myRoomId in self.server.chatRooms.keys():
            print('Chat room id is already being used.')
            data = {
                'header': HEADER,
                'type': "DONE",
                'content': "Chat Room ID already in use."
            }
            self.server.send(self.conn, data)

        else:
            usersInChat = {self.clientId: self.clientName}
            chatroomInfo = {
                'ownerId': self.clientId,
                'usersInChat': usersInChat,
                'messages': [{self.clientName: f'{self.clientName} has created chat room {myRoomId}'}]
            }
            self.server.chatRooms[myRoomId] = chatroomInfo
            chatRoomContent = f'----------------------- Chat Room {myRoomId}------------------------\nType exit to close the chat room.\nChat room created by: {self.clientNames[self.clientId]}\nWaiting for other users to join....\n'
            for x in self.server.chatRooms[myRoomId]['messages']:
                for key, value in x.items():
                    chatRoomContent += f'{key}>{value}'
            data = {
                'header': HEADER,
                'type': "NEEDMORE",
                'content': chatRoomContent,
                'infoNeeded': {'chatmessage': ["string", f"{self.clientName}> "]}
            }
            self.server.send(self.conn, data)
            while True:
                try:
                    clientResponse = self.server.receive(self.conn)
                    self.server.chatRooms[myRoomId]['messages'].append(
                        {self.clientName: clientResponse['chatmessage']})
                except:
                    print(f'{self.clientName} has disconnected')
                    # data = {
                    #     'header': HEADER,
                    #     'type': "DONE",
                    #     'content': "Disconnecting client from server and removing chat room"
                    # }
                    # self.server.send(self.conn, data)
                    break

                if clientResponse['chatmessage'] == "exit":
                    data = {
                        'header': HEADER,
                        'type': "DONE",
                        'content': "Disconnecting client from chat room and removing chat room"
                    }
                    del self.server.chatRooms[myRoomId]
                    self.server.send(self.conn, data)
                    break
                else:
                    chatRoomContent = f'----------------------- Chat Room {myRoomId}------------------------\nType exit to close the chat room.\nChat room created by: {self.clientNames[self.clientId]}\nWaiting for other users to join....\n'
                    for x in self.server.chatRooms[myRoomId]['messages']:
                        for key, value in x.items():
                            chatRoomContent += f'{key}>{value}\n'
                    data = {
                        'header': HEADER,
                        'type': "NEEDMORE",
                        'content': chatRoomContent,
                        'infoNeeded': {'chatmessage': ["string", f"{self.clientName}> "]}
                    }
                    self.server.send(self.conn, data)

    def _join_chat(self, joinedRoom):
        """
        TODO: join a chat in a existing room
        :param joinedRoom:
        :return: VOID
        """
        if (joinedRoom in self.server.chatRooms.keys()):
            self.server.chatRooms[joinedRoom]['usersInChat'][self.clientId] = self.clientName

            chatmessages = f"----------------------- Chat Room {joinedRoom} ------------------------\n"
            chatmessages += "Type 'bye' to exit this chat room\n"
            # Add join message to chatroom messages
            self.server.chatRooms[joinedRoom]['messages'].append(
                {self.clientName: f"{self.clientName} has joined chat room {joinedRoom}"})

            # Display all messages
            for x in self.server.chatRooms[joinedRoom]['messages']:
                for key, value in x.items():
                    chatmessages += f"{key}>{value}\n"

            response = {
                'header': HEADER,
                'type': "NEEDMORE",
                'content': chatmessages,
                'infoNeeded': {'chatmessage': ["string", f"{self.clientName}> "]}
            }
            self.server.send(self.conn, response)
            # Recieve connection with infoNeeded aka chat message, process that by addingto messages
            while True:
                try:
                    clientResponse = self.server.receive(self.conn)
                except:
                    self.server.chatRooms[joinedRoom]['messages'].append(
                        {self.clientName: f"{self.clientName} is leaving chat room {joinedRoom}"})
                    del self.server.chatRooms[joinedRoom]['usersInChat'][self.clientId]
                    break

                chatmessage = clientResponse['chatmessage']
                # Add the message to chatmessages response (appears to be live)
                chatmessages = f"----------------------- Chat Room {joinedRoom} ------------------------\n"
                chatmessages += "Type 'bye' to exit this chat room\n"
                if joinedRoom not in self.server.chatRooms.keys():
                    leave = {
                        'header': HEADER,
                        'type': "DONE",
                        'content': None
                    }
                    self.server.send(self.conn, leave)
                    break
                self.server.chatRooms[joinedRoom]['messages'].append(
                    {self.clientName: f"{chatmessage}"})
                # Display all messages
                for x in self.server.chatRooms[joinedRoom]['messages']:
                    for key, value in x.items():
                        chatmessages += f"{key}>{value}\n"
                        if key == self.clientNames[self.server.chatRooms[joinedRoom]['ownerId']] and value == 'exit':
                            leave = {
                                'header': HEADER,
                                'type': "DONE",
                                'content': None
                            }
                            self.server.send(self.conn, leave)
                            break

                if chatmessage == "bye":
                    self.server.chatRooms[joinedRoom]['messages'].append(
                        {self.clientName: f"{self.clientName} is leaving chat room {joinedRoom}"})
                    del self.server.chatRooms[joinedRoom]['usersInChat'][self.clientId]
                    leave = {
                        'header': HEADER,
                        'type': "DONE",
                        'content': None
                    }
                    self.server.send(self.conn, leave)
                    break

                else:
                    needmore = {
                        'header': HEADER,
                        'type': "NEEDMORE",
                        'content': chatmessages,
                        'infoNeeded': {'chatmessage': ["string", f"{self.clientName}> "]}
                    }
                    self.server.send(self.conn, needmore)

        else:
            print("This chat room does NOT exist.")
            response = {
                'header': HEADER,
                'type': "DONE",
                'content': 'The chat room you entered does not exist'
            }
            self.server.send(self.conn, response)

    def delete_client_data(self):
        """
        TODO: delete all the data related to this client from the server.
        :return: VOID
        """
        self.serverIp = None
        self.clientId = None
        self.conn = None
        self.unreadMessages = None
        self.clientNames = None

    def _disconnect_from_server(self):
        """
        TODO: call delete_client_data() method, and then, disconnect this client from the server.
        :return: VOID
        """
        print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        print(
            f'Disconnecting user: {self.clientNames[self.clientId]} {self.serverIp}/{self.clientId}')
        print("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
        # Sets up exit acknowledgement to client and closed the socket breaks the loop for the thread
        data = {
            'header': HEADER,
            'type': "EXIT",
            'content': None
        }
        self.server.send(self.conn, data)
        self.delete_client_data()
