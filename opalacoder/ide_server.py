import asyncio
import os
import json
import urllib.parse
import mimetypes

def get_file_tree(dir_path, root_path=None):
    if root_path is None:
        root_path = dir_path
    
    files = []
    try:
        items = os.listdir(dir_path)
    except Exception:
        return []
        
    for item in items:
        # Skip heavy/hidden directories
        if item in ['node_modules', '.git', '.venv', '.env', '__pycache__', '.pytest_cache']:
            continue
            
        full_path = os.path.join(dir_path, item)
        rel_path = os.path.relpath(full_path, root_path)
        
        is_dir = os.path.isdir(full_path)
        if is_dir:
            files.append({
                "name": item,
                "path": rel_path,
                "isDirectory": True,
                "children": get_file_tree(full_path, root_path)
            })
        else:
            files.append({
                "name": item,
                "path": rel_path,
                "isDirectory": False
            })
            
    # Sort: directories first, then alphabetical
    files.sort(key=lambda x: (not x["isDirectory"], x["name"].lower()))
    return files

class AsyncHTTPServer:
    def __init__(self, host="127.0.0.1", port=3000, static_dir=None):
        self.host = host
        self.port = port
        self.static_dir = static_dir
        self.active_queues = []

    async def start(self):
        self.server = await asyncio.start_server(self.handle_request, self.host, self.port)
        print(f"[IDE Backend] Python Async server running on http://{self.host}:{self.port}")

    async def handle_request(self, reader, writer):
        try:
            # Read request line
            request_line = await reader.readline()
            if not request_line:
                writer.close()
                return
                
            parts = request_line.decode('utf-8').strip().split()
            if len(parts) < 3:
                writer.close()
                return
                
            method, raw_path, _ = parts
            parsed_url = urllib.parse.urlparse(raw_path)
            path = parsed_url.path
            query = urllib.parse.parse_qs(parsed_url.query)
            
            # Read headers
            headers = {}
            while True:
                line = await reader.readline()
                line = line.decode('utf-8').strip()
                if not line:
                    break
                if ':' in line:
                    k, v = line.split(':', 1)
                    headers[k.strip().lower()] = v.strip()
                
            # Read body if Content-Length exists
            body = b""
            if 'content-length' in headers:
                content_length = int(headers['content-length'])
                body = await reader.readexactly(content_length)
                
            # Handle OPTIONS (CORS)
            if method == 'OPTIONS':
                self.send_cors(writer)
                return
                
            # Route API paths
            if path.startswith('/api/'):
                await self.route_api(method, path, query, headers, body, writer)
            else:
                # Serve static files
                await self.serve_static(path, writer)
                
        except Exception as e:
            print(f"Error handling request: {e}")
            try:
                writer.close()
            except:
                pass

    def send_response(self, writer, status_code, body, content_type="text/plain"):
        status_msg = "OK" if status_code == 200 else ("Not Found" if status_code == 404 else "Error")
        headers = (
            f"HTTP/1.1 {status_code} {status_msg}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Connection: close\r\n\r\n"
        )
        writer.write(headers.encode('utf-8'))
        writer.write(body)
        writer.close()

    def send_cors(self, writer):
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(headers.encode('utf-8'))
        writer.close()

    async def serve_static(self, path, writer):
        if not self.static_dir:
            self.send_response(writer, 404, b"Not Found")
            return
            
        # Clean path and prevent directory traversal
        rel_path = path.lstrip('/')
        if not rel_path or rel_path == '':
            rel_path = 'index.html'
            
        full_path = os.path.abspath(os.path.join(self.static_dir, rel_path))
        if not full_path.startswith(os.path.abspath(self.static_dir)):
            self.send_response(writer, 403, b"Forbidden")
            return
            
        if not os.path.exists(full_path) or os.path.isdir(full_path):
            # For SPA router fallback to index.html
            full_path = os.path.join(self.static_dir, 'index.html')
            
        try:
            with open(full_path, 'rb') as f:
                content = f.read()
            mime_type, _ = mimetypes.guess_type(full_path)
            mime_type = mime_type or 'application/octet-stream'
            
            headers = f"HTTP/1.1 200 OK\r\nContent-Type: {mime_type}\r\nContent-Length: {len(content)}\r\nConnection: close\r\n\r\n"
            writer.write(headers.encode('utf-8'))
            writer.write(content)
            await writer.drain()
            writer.close()
        except Exception as e:
            self.send_response(writer, 500, f"Error: {e}".encode('utf-8'))

    async def route_api(self, method, path, query, headers, body, writer):
        # Parse JSON body if present
        data = {}
        if body:
            try:
                data = json.loads(body.decode('utf-8'))
            except:
                pass

        # 1. List Files
        if path == '/api/files':
            project_path = query.get('projectPath', [None])[0]
            if not project_path:
                self.send_response(writer, 400, b'{"error":"projectPath parameter is required"}', "application/json")
                return
            if not os.path.exists(project_path) or not os.path.isdir(project_path):
                self.send_response(writer, 404, b'{"error":"Directory not found"}', "application/json")
                return
            try:
                tree = get_file_tree(project_path)
                self.send_response(writer, 200, json.dumps({"files": tree}).encode('utf-8'), "application/json")
            except Exception as e:
                self.send_response(writer, 500, json.dumps({"error": str(e)}).encode('utf-8'), "application/json")

        # 2. Read File
        elif path == '/api/file/read':
            project_path = query.get('projectPath', [None])[0]
            file_path = query.get('filePath', [None])[0]
            if not project_path or not file_path:
                self.send_response(writer, 400, b'{"error":"projectPath and filePath are required"}', "application/json")
                return
            full_path = os.path.abspath(os.path.join(project_path, file_path))
            if not full_path.startswith(os.path.abspath(project_path)):
                self.send_response(writer, 403, b'{"error":"Forbidden: Path traversal detected"}', "application/json")
                return
            if not os.path.exists(full_path) or os.path.isdir(full_path):
                self.send_response(writer, 404, b'{"error":"File not found"}', "application/json")
                return
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(writer, 200, json.dumps({"content": content}).encode('utf-8'), "application/json")
            except Exception as e:
                self.send_response(writer, 500, json.dumps({"error": str(e)}).encode('utf-8'), "application/json")

        # 3. Write File
        elif path == '/api/file/write' and method == 'POST':
            project_path = data.get('projectPath')
            file_path = data.get('filePath')
            content = data.get('content', '')
            if not project_path or not file_path:
                self.send_response(writer, 400, b'{"error":"projectPath and filePath are required"}', "application/json")
                return
            full_path = os.path.abspath(os.path.join(project_path, file_path))
            if not full_path.startswith(os.path.abspath(project_path)):
                self.send_response(writer, 403, b'{"error":"Forbidden: Path traversal detected"}', "application/json")
                return
            try:
                dir_path = os.path.dirname(full_path)
                os.makedirs(dir_path, exist_ok=True)
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.send_response(writer, 200, b'{"success":true}', "application/json")
            except Exception as e:
                self.send_response(writer, 500, json.dumps({"error": str(e)}).encode('utf-8'), "application/json")

        # 3.5. Delete File
        elif path == '/api/file/delete' and method == 'POST':
            project_path = data.get('projectPath')
            file_path = data.get('filePath')
            if not project_path or not file_path:
                self.send_response(writer, 400, b'{"error":"projectPath and filePath are required"}', "application/json")
                return
            full_path = os.path.abspath(os.path.join(project_path, file_path))
            if not full_path.startswith(os.path.abspath(project_path)):
                self.send_response(writer, 403, b'{"error":"Forbidden: Path traversal detected"}', "application/json")
                return
            try:
                if os.path.exists(full_path):
                    if os.path.isdir(full_path):
                        import shutil
                        shutil.rmtree(full_path)
                    else:
                        os.remove(full_path)
                    self.send_response(writer, 200, b'{"success":true}', "application/json")
                else:
                    self.send_response(writer, 404, b'{"error":"File not found"}', "application/json")
            except Exception as e:
                self.send_response(writer, 500, json.dumps({"error": str(e)}).encode('utf-8'), "application/json")

        # 4. List Projects
        elif path == '/api/opalacoder/list-projects':
            from opalacoder.config import DEFAULT_DB_PATH
            from opalacoder.project import ProjectStore
            store = ProjectStore(db_path=DEFAULT_DB_PATH)
            projects = store.list_projects()
            self.send_response(writer, 200, json.dumps({"projects": projects}).encode('utf-8'), "application/json")

        # 5. Create Project
        elif path == '/api/opalacoder/create-project' and method == 'POST':
            from opalacoder.config import DEFAULT_DB_PATH, DEFAULT_MODEL
            from opalacoder.project import ProjectStore
            store = ProjectStore(db_path=DEFAULT_DB_PATH)
            
            project_name = data.get("project_name")
            project_path = data.get("project_path") or os.getcwd()
            description = data.get("description", "")
            model = data.get("model") or DEFAULT_MODEL
            mode = data.get("mode") or "auto"
            skills = data.get("skills", [])
            api_key = data.get("api_key")
            api_base = data.get("api_base")
            
            if not project_name:
                self.send_response(writer, 400, b'{"error":"project_name is required"}', "application/json")
                return
                
            db_key = project_name.replace(" ", "_").lower()
            if store.exists(db_key):
                db_key = db_key + "_1"
                
            try:
                project = store.create(
                    name=db_key,
                    mode=mode,
                    model=model,
                    project_name=project_name,
                    project_path=os.path.abspath(project_path),
                    skills=skills,
                    description=description,
                    api_key=api_key,
                    api_base=api_base,
                )
                res_data = {
                    "project_name": project.project_name,
                    "project_path": project.project_path,
                    "skills": project.skills
                }
                self.send_response(writer, 200, json.dumps(res_data).encode('utf-8'), "application/json")
            except Exception as e:
                self.send_response(writer, 500, json.dumps({"error": str(e)}).encode('utf-8'), "application/json")

        # 6. Delete Project
        elif path == '/api/opalacoder/delete' and method == 'POST':
            from opalacoder.config import DEFAULT_DB_PATH
            from opalacoder.project import ProjectStore
            store = ProjectStore(db_path=DEFAULT_DB_PATH)
            project_name = data.get("project_name")
            if not project_name:
                self.send_response(writer, 400, b'{"error":"project_name is required"}', "application/json")
                return
            if store.exists(project_name):
                store.delete(project_name)
                self.send_response(writer, 200, b'{"success":true}', "application/json")
            else:
                self.send_response(writer, 404, json.dumps({"error": f"Project '{project_name}' not found"}).encode('utf-8'), "application/json")

        # 7a. Input Response (resolves a pending GUI confirm/ask request)
        elif path == '/api/opalacoder/input_response' and method == 'POST':
            req_id = data.get("id", "")
            value = data.get("value", "")
            from opalacoder.agent_stdin import _gui_input_pending
            fut = _gui_input_pending.get(req_id)
            if fut and not fut.done():
                fut.get_loop().call_soon_threadsafe(fut.set_result, value)
                self.send_response(writer, 200, b'{"ok":true}', "application/json")
            else:
                self.send_response(writer, 404, b'{"error":"No pending request with that id"}', "application/json")
            return

        # 7b. Run Agent (Streaming)
        elif path == '/api/opalacoder/run' and method == 'POST':

            headers = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/plain\r\n"
                "Transfer-Encoding: chunked\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Cache-Control: no-cache\r\n"
                "Connection: keep-alive\r\n\r\n"
            )
            writer.write(headers.encode('utf-8'))
            await writer.drain()

            event_queue = asyncio.Queue()
            self.active_queues.append(event_queue)

            def send_chunk(text: str):
                chunk = text.encode('utf-8')
                if not chunk:
                    return
                writer.write(f"{len(chunk):X}\r\n".encode('utf-8'))
                writer.write(chunk)
                writer.write(b"\r\n")

            from opalacoder.agent_stdin import handle_run
            
            async def run_agent():
                try:
                    await handle_run(data)
                except Exception as e:
                    import traceback
                    err_msg = traceback.format_exc()
                    event_queue.put_nowait({"event": "error", "message": str(e), "trace": err_msg})
                finally:
                    event_queue.put_nowait(None)

            agent_task = asyncio.create_task(run_agent())

            try:
                while True:
                    event = await event_queue.get()
                    if event is None:
                        break
                    send_chunk(json.dumps(event) + "\n")
                    await writer.drain()
            except Exception as e:
                print(f"Streaming error: {e}")
            finally:
                if event_queue in self.active_queues:
                    self.active_queues.remove(event_queue)
                writer.write(b"0\r\n\r\n")
                await writer.drain()
                writer.close()
                await agent_task
        else:
            self.send_response(writer, 404, b'{"error":"Not Found"}', "application/json")

def start_gui_server(host="127.0.0.1", port=3000):
    # Path to gui directory inside opalacoder package
    package_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(package_dir, "gui")
    
    if not os.path.exists(static_dir):
        print(f"Warning: GUI static assets directory not found at {static_dir}. Server will run API-only.")
        static_dir = None
        
    server = AsyncHTTPServer(host=host, port=port, static_dir=static_dir)
    
    import opalacoder.agent_stdin as agent_stdin
    
    def web_event_hook(payload):
        for q in server.active_queues:
            q.put_nowait(payload)
            
    agent_stdin.event_hook = web_event_hook
    
    async def run_server():
        await server.start()
        # Open browser automatically
        import webbrowser
        webbrowser.open(f"http://{host}:{port}")
        # Keep running
        while True:
            await asyncio.sleep(3600)
            
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\nStopping OpalaCoder IDE Server...")
