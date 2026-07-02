#######################################################################
# File:             client_handler.py
# Author:           George Freedland
# Purpose:          CSC645 Assigment #1 TCP socket programming
# Description:      Handles a single client connection on the server.
# Running:          python3 server.py
#                   Note: Must run the server before the client.
########################################################################
import socket
import pickle
import logging

log = logging.getLogger('server')

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
        # Register the per-connection send lock before any data is sent so
        # that every write to this socket is serialized.
        server_instance.register_connection(conn)
        server_instance.clientHandlerObjects[addr[1]] = conn

        # Send the clientId to the client and receive the name back, then send an ok response.
        server_instance.sendClientId(conn, addr[1])
        server_instance.receiveClientName(conn, addr[1])
        server_instance.sendOk(conn)

        self.clientNames = server_instance.clientNames
        self.clientName = server_instance.clientNames.get(addr[1], str(addr[1]))
        self.unreadMessages = server_instance.unreadMessages
        self.myRoomId = None

    def _sendMenu(self):
        """
        Sends the menu options to the client after the handshake between client and server is done.
        :return: VOID
        """
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
                if clientResponse is None:
                    return
                recipientId = clientResponse['recipientId']
                message = clientResponse['message']
                self._send_message(recipientId, message)
            elif option == 3:
                self._show_messages()
            elif option == 4:
                infoNeeded = {
                    'myRoomId': ["int", "Enter the room id you want to create: "]
                }
                response['infoNeeded'] = infoNeeded
                self.server.send(self.conn, response)
                clientResponse = self.server.receive(self.conn)
                if clientResponse is None:
                    return
                self._create_chat(clientResponse['myRoomId'])
            elif option == 5:
                infoNeeded = {
                    'joinRoomId': ["int", "Enter the room id you want to join: "]
                }
                response['infoNeeded'] = infoNeeded
                self.server.send(self.conn, response)
                clientResponse = self.server.receive(self.conn)
                if clientResponse is None:
                    return
                self._join_chat(clientResponse['joinRoomId'])
            elif option == 6:
                infoNeeded = {
                    'broadcastMessage': ["string", "Enter the message to broadcast to all users: "]
                }
                response['infoNeeded'] = infoNeeded
                self.server.send(self.conn, response)
                clientResponse = self.server.receive(self.conn)
                if clientResponse is None:
                    return
                self._broadcast_message(clientResponse['broadcastMessage'])
            elif option == 7:
                self._disconnect_from_server()
        else:
            log.warning(f"Client {self.clientId} selected an invalid option")
            self._sendMenu()

    # When a DONE type is sent, the content is displayed. clientNames is updated at every login/logout.
    def _send_user_list(self):
        log.info(f"Sending user list to {self.clientName}")

        users = "\n".join(
            f"  id {cid}: {name}" for cid, name in self.clientNames.items())
        data = {
            'header': HEADER,
            'type': "DONE",
            'content': 'Users in the server:\n' + users
        }
        self.server.send(self.conn, data)
        return None

    # Delivers a direct message to a recipient in real time (if connected) and
    # stores it in the mailbox so it can also be read later via option 3.
    def _send_message(self, recipientId, message):
        # Normalize to int so it matches the integer client ids used as keys
        # in clientNames and compared against in _show_messages.
        try:
            recipientId = int(recipientId)
        except (TypeError, ValueError):
            recipientId = None

        if recipientId in self.clientNames.keys():
            log.info(f"{self.clientName} -> {recipientId}: {message}")
            self.unreadMessages.append({
                'recipient': recipientId, 'messagecontent': message,
                'sender': self.clientId, 'unread': True})

            # Push the message to the recipient right now if they're connected.
            recipient_conn = self.server.clientHandlerObjects.get(recipientId)
            if recipient_conn is not None:
                self._push(recipient_conn,
                           f"[Message from {self.clientName}] {message}")

            data = {
                'header': HEADER,
                'type': "DONE",
                'content': f'Message sent to id {recipientId}: {message}'
            }
            self.server.send(self.conn, data)
        else:
            log.info(f"{self.clientName} tried to message unknown id {recipientId}")
            data = {
                'header': HEADER,
                'type': "DONE",
                'content': 'The recipient you entered does not exist'
            }
            self.server.send(self.conn, data)

    def _broadcast_message(self, message):
        """
        Sends a message from this client to every other connected client in
        real time. The sender gets a confirmation instead of the push so the
        message isn't shown twice on their screen.
        :param message: the text to broadcast.
        :return: VOID
        """
        broadcastContent = f"[BROADCAST] {self.clientName}: {message}"
        log.info(f"Broadcast from {self.clientName}: {message}")

        for recipientId, conn in list(self.server.clientHandlerObjects.items()):
            if recipientId == self.clientId:
                continue
            self._push(conn, broadcastContent)

        self.server.send(self.conn, {
            'header': HEADER,
            'type': "DONE",
            'content': f'Broadcast sent to all users: {message}'
        })

    def _push(self, conn, text):
        """Sends an unsolicited (asynchronous) message that the receiving
        client should display immediately, interrupting whatever prompt the
        user is at."""
        data = {'header': HEADER, 'type': "PUSH", 'content': text}
        try:
            self.server.send(conn, data)
        except (socket.error, OSError):
            log.warning("Could not deliver a push message (client gone).")

    def _show_messages(self):
        """
        Sends all the unread messages of this client. Messages are removed from
        the mailbox once they've been read.
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

    # ------------------------------------------------------------------
    # Chat rooms
    #
    # A room lives as long as it has at least one member. Any member can leave
    # by typing 'exit' or 'bye'. Every message (and join/leave notice) is
    # pushed to all other members in real time.
    #
    # chatRooms[roomId] = {
    #     'ownerId': <creator id>,
    #     'members': {clientId: {'name': name, 'conn': conn}},
    #     'messages': [(senderName, text), ...],
    # }
    # ------------------------------------------------------------------
    def _room_header(self, roomId):
        room = self.server.chatRooms[roomId]
        lines = [
            f"----------------------- Chat Room {roomId} -----------------------",
            "Type 'exit' or 'bye' to leave the room.",
        ]
        for name, text in room['messages']:
            lines.append(f"{name}> {text}")
        return "\n".join(lines)

    def _create_chat(self, myRoomId):
        """
        Creates a new chat room and drops this client into it.
        :param myRoomId: the id for the new room.
        :return: VOID
        """
        if myRoomId in self.server.chatRooms.keys():
            log.info(f"Chat room {myRoomId} already exists")
            self.server.send(self.conn, {
                'header': HEADER,
                'type': "DONE",
                'content': "Chat Room ID already in use."
            })
            return

        self.myRoomId = myRoomId
        self.server.chatRooms[myRoomId] = {
            'ownerId': self.clientId,
            'members': {self.clientId: {'name': self.clientName, 'conn': self.conn}},
            'messages': [('*', f"{self.clientName} created chat room {myRoomId}")],
        }
        log.info(f"{self.clientName} created chat room {myRoomId}")

        self.server.send(self.conn, {
            'header': HEADER,
            'type': "CHATSTART",
            'content': self._room_header(myRoomId)
        })
        self._chat_session(myRoomId)

    def _join_chat(self, joinedRoom):
        """
        Joins an existing chat room and drops this client into it.
        :param joinedRoom: the id of the room to join.
        :return: VOID
        """
        if joinedRoom not in self.server.chatRooms.keys():
            log.info(f"{self.clientName} tried to join unknown room {joinedRoom}")
            self.server.send(self.conn, {
                'header': HEADER,
                'type': "DONE",
                'content': 'The chat room you entered does not exist'
            })
            return

        room = self.server.chatRooms[joinedRoom]
        room['members'][self.clientId] = {
            'name': self.clientName, 'conn': self.conn}
        room['messages'].append(
            ('*', f"{self.clientName} joined the room"))
        log.info(f"{self.clientName} joined chat room {joinedRoom}")

        # Let everyone already in the room know, in real time.
        self._push_to_room(
            joinedRoom, f"*** {self.clientName} joined the room ***",
            exclude=self.clientId)

        self.server.send(self.conn, {
            'header': HEADER,
            'type': "CHATSTART",
            'content': self._room_header(joinedRoom)
        })
        self._chat_session(joinedRoom)

    def _chat_session(self, roomId):
        """
        Blocking loop (runs in this client's thread) that reads chat lines from
        the client and pushes them to the rest of the room until the client
        leaves or disconnects.
        """
        while True:
            try:
                resp = self.server.receive(self.conn)
            except (socket.error, EOFError, pickle.UnpicklingError):
                resp = None

            # Client disconnected mid-chat: leave the room and let the outer
            # handler loop perform the final cleanup.
            if resp is None:
                self._leave_room(roomId)
                return

            text = str(resp.get('content', '')).strip()

            if text.lower() in ('exit', 'bye'):
                self._leave_room(roomId)
                return

            room = self.server.chatRooms.get(roomId)
            if room is None:
                return

            room['messages'].append((self.clientName, text))
            self._push_to_room(
                roomId, f"{self.clientName}> {text}", exclude=self.clientId)

    def _leave_room(self, roomId):
        room = self.server.chatRooms.get(roomId)
        if not room:
            return

        room['members'].pop(self.clientId, None)
        log.info(f"{self.clientName} left chat room {roomId}")

        if room['members']:
            room['messages'].append(
                ('*', f"{self.clientName} left the room"))
            self._push_to_room(
                roomId, f"*** {self.clientName} left the room ***")
        else:
            del self.server.chatRooms[roomId]
            log.info(f"Chat room {roomId} is empty and was removed")

    def _push_to_room(self, roomId, text, exclude=None):
        room = self.server.chatRooms.get(roomId)
        if not room:
            return
        for memberId, info in list(room['members'].items()):
            if memberId == exclude:
                continue
            self._push(info['conn'], text)

    def delete_client_data(self):
        """
        Clears the references this handler holds for the client.
        :return: VOID
        """
        self.serverIp = None
        self.clientId = None
        self.conn = None
        self.unreadMessages = None
        self.clientNames = None

    def _disconnect_from_server(self):
        """
        Acknowledges the client's disconnect request and clears its data.
        :return: VOID
        """
        log.info(
            f"Disconnecting user: {self.clientName} {self.serverIp}/{self.clientId}")
        data = {
            'header': HEADER,
            'type': "EXIT",
            'content': None
        }
        self.server.send(self.conn, data)
        self.delete_client_data()
