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
- The server spawns one thread per connected client (up to `MAX_NUM_CONN`) and
  serializes all writes to a socket with a per-connection lock.
- **Real-time delivery:** the client runs a background *receiver thread* that
  is always listening. When the server pushes a message (a chat line, a
  broadcast, or a direct message), it appears immediately — the client clears
  the current prompt, prints the incoming message, and restores whatever you
  were typing so you can keep going.
- The server logs every event on a single timestamped line (e.g.
  `[20:54:37] Alice created chat room 100`), so the console is easy to scan.

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
[20:54:36] Server is starting....
[20:54:36] Clients on this machine can connect using IP 127.0.0.1 and port 12000
[20:54:36] Clients on your LAN can connect using IP 192.168.x.x and port 12000
[20:54:36] Listening at 192.168.x.x:12000
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

If the address or port is wrong, the client gives up after **30 seconds** (or
sooner if the connection is refused) with a message explaining why, instead of
hanging forever.

Run `python3 client.py` again in more terminals to connect additional clients
and try messaging/broadcasting between them.

## Menu options

Once connected, each client sees:

1. **Get user list** – list everyone currently connected (with their ids).
2. **Send a message** – send a direct message to another user by their id. It's
   delivered to them **in real time** if they're online, and also stored so they
   can read it later with option 3.
3. **Get my messages** – read (and clear) your unread direct messages.
4. **Create a new chat room** – open a room others can join, then start chatting.
5. **Join an existing chat room** – join a room by id and chat in real time.
6. **Broadcast a message to all users** – push one message to every connected
   client at the same time (prefixed with `[BROADCAST]`).
7. **Disconnect from server** – cleanly leave the server.

### Chat rooms

- Create (option 4) or join (option 5) a room, then just type and press Enter to
  send. Messages from other members show up live.
- A room stays open as long as at least one member is in it. Type `exit` or `bye`
  to leave; when the last member leaves, the room is removed automatically.

## Notes

- Broadcasts, direct messages, and chat lines are pushed to other clients
  instantly; the receiving client interrupts its current prompt to show the
  message and then restores what you were typing.
- To stop the server, press `Ctrl+C` in its terminal.
