# TCP-IP-Centralized-Server

**Author:** George Freedland

A functional client–server centralized network that provides messaging/chat
services to multiple clients over TCP/IP. A single multithreaded server accepts
many clients at once and offers a menu-driven set of services: listing users,
sending direct messages, reading your messages, creating/joining chat rooms, and
**broadcasting a message to every connected client at once**.

## Requirements

- Python 3.8+ (developed and tested on 3.8–3.12)
- No third-party dependencies — everything uses the Python standard library
  (`socket`, `struct`, `threading`, `pickle`).

## How it works

- Messages are Python dictionaries serialized with `pickle`.
- Every message is sent with a **4-byte big-endian length prefix** so the
  receiver always reads exactly one complete message. This prevents messages
  from being split or merged on the TCP stream (a common source of bugs when
  reading a fixed number of bytes).
- The server spawns one thread per connected client (up to `MAX_NUM_CONN`).

## Running locally

The code lives in `TCP-Client-Server-Centralized-Network/`. Open **two
terminals** (one for the server, one or more for clients).

### 1. Start the server

```bash
cd TCP-Client-Server-Centralized-Network/server
python3 server.py
```

The server binds to `0.0.0.0:12000` and prints the addresses clients can use,
for example:

```
Server is starting....
Clients on this machine can connect using IP 127.0.0.1 and port 12000
Clients on your LAN can connect using IP 192.168.x.x and port 12000
Listening at  192.168.x.x / 12000
```

### 2. Start one or more clients

In another terminal:

```bash
cd TCP-Client-Server-Centralized-Network/client
python3 client.py
```

You'll be prompted for connection details:

- **Server IP Address:** `127.0.0.1` if the client is on the same machine as the
  server, or the printed LAN IP if it's on another machine on the same network.
- **Server port:** `12000`
- **Your id key (i.e. your name):** any display name, e.g. `Alice`

Run `python3 client.py` again in more terminals to connect additional clients
and try messaging/broadcasting between them.

## Menu options

Once connected, each client sees:

1. **Get user list** – list everyone currently connected.
2. **Send a message** – send a direct message to another user by their id.
3. **Get my messages** – read (and clear) your unread direct messages.
4. **Create a new chat room** – open a room others can join.
5. **Join an existing chat room** – join a room by id.
6. **Broadcast a message to all users** – send one message to every connected
   client at the same time (prefixed with `[BROADCAST]`).
7. **Disconnect from server** – cleanly leave the server.

## Notes

- Because the protocol is request/response, a broadcast is delivered to other
  clients the next time they interact with the server (best-effort), and always
  to the sender immediately as confirmation.
- To stop the server, press `Ctrl+C` in its terminal.
