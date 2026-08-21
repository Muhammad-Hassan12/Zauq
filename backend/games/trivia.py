import random
import logging
from typing import Dict, Any, List
from backend.memory.rag import search_server_lore

logger = logging.getLogger("zauq.trivia")

TECH_TRIVIA_BANK = [
    # EASY TIER
    {
        "difficulty": "easy",
        "question": "What does HTTP status code 418 signify?",
        "options": [
            "Forbidden Access",
            "I'm a teapot (RFC 2324 / RFC 7168)",
            "Gateway Timeout",
            "Unprocessable Entity"
        ],
        "correct_index": 1,
        "explanation": "HTTP 418 I'm a teapot was defined in 1998 as an April Fools' joke in RFC 2324."
    },
    {
        "difficulty": "easy",
        "question": "Which data structure operates on a First-In, First-Out (FIFO) principle?",
        "options": [
            "Stack",
            "Queue",
            "Binary Tree",
            "Heap"
        ],
        "correct_index": 1,
        "explanation": "Queues process items in FIFO order, whereas Stacks operate on LIFO (Last-In, First-Out)."
    },
    {
        "difficulty": "easy",
        "question": "Which Git command is used to combine changes from one branch into another?",
        "options": [
            "git merge",
            "git clone",
            "git push",
            "git init"
        ],
        "correct_index": 0,
        "explanation": "git merge combines the specified branch's commit history into the current active branch."
    },
    {
        "difficulty": "easy",
        "question": "Which port is used by default for unencrypted HTTP traffic?",
        "options": [
            "443",
            "80",
            "8080",
            "22"
        ],
        "correct_index": 1,
        "explanation": "Port 80 is the standard default port for HTTP traffic, while Port 443 is used for secure HTTPS."
    },
    {
        "difficulty": "easy",
        "question": "In Python, which keyword is used to define an anonymous inline function?",
        "options": [
            "def",
            "inline",
            "lambda",
            "func"
        ],
        "correct_index": 2,
        "explanation": "The 'lambda' keyword creates small anonymous single-expression functions in Python."
    },
    {
        "difficulty": "easy",
        "question": "What does SQL stand for in database management?",
        "options": [
            "Structured Query Language",
            "Sequential Quick Logic",
            "Standard Question Language",
            "Simple Query Logic"
        ],
        "correct_index": 0,
        "explanation": "SQL stands for Structured Query Language, the domain-specific standard for relational databases."
    },
    {
        "difficulty": "easy",
        "question": "What is the file extension typically used for Docker configuration files?",
        "options": [
            ".docker",
            "Dockerfile (no extension)",
            ".dock",
            ".compose"
        ],
        "correct_index": 1,
        "explanation": "Docker build instruction files are conventionally named 'Dockerfile' without any file extension."
    },
    {
        "difficulty": "easy",
        "question": "Which of the following is an in-memory key-value data store frequently used for caching?",
        "options": [
            "PostgreSQL",
            "Redis",
            "MySQL",
            "Oracle"
        ],
        "correct_index": 1,
        "explanation": "Redis is an open-source, in-memory data structure store used as a database, cache, and message broker."
    },
    {
        "difficulty": "easy",
        "question": "In Linux, which command is used to display the current working directory path?",
        "options": [
            "pwd",
            "ls",
            "cd",
            "whereami"
        ],
        "correct_index": 0,
        "explanation": "pwd stands for 'Print Working Directory' and prints the full absolute path of the current directory."
    },
    {
        "difficulty": "easy",
        "question": "What does JSON stand for in web development?",
        "options": [
            "Java Syntax Object Notation",
            "JavaScript Object Notation",
            "Jupyter Sequential Online Nodes",
            "Joint System Output Network"
        ],
        "correct_index": 1,
        "explanation": "JSON stands for JavaScript Object Notation, a lightweight data-interchange text format."
    },
    {
        "difficulty": "easy",
        "question": "Which HTML tag is used to create a clickable hyperlink?",
        "options": [
            "<link>",
            "<a>",
            "<href>",
            "<url>"
        ],
        "correct_index": 1,
        "explanation": "The <a> (anchor) element with the 'href' attribute creates hyperlinks to other web pages or files."
    },
    {
        "difficulty": "easy",
        "question": "Which command-line package manager is used by default in Node.js environments?",
        "options": [
            "pip",
            "npm",
            "cargo",
            "gem"
        ],
        "correct_index": 1,
        "explanation": "npm (Node Package Manager) is the default package manager for the JavaScript runtime Node.js."
    },
    {
        "difficulty": "easy",
        "question": "What is the main purpose of the '.gitignore' file in a software repository?",
        "options": [
            "To delete untracked files automatically",
            "To specify intentionally untracked files that Git should ignore",
            "To encrypt sensitive passwords in commits",
            "To compress the repository commit history"
        ],
        "correct_index": 1,
        "explanation": ".gitignore patterns prevent specified files (e.g. node_modules, .env, __pycache__) from being tracked by Git."
    },

    # MEDIUM TIER
    {
        "difficulty": "medium",
        "question": "What is the primary execution model of Python's GIL (Global Interpreter Lock)?",
        "options": [
            "Ensures only one thread executes Python bytecode at a time",
            "Compiles Python code directly to machine code",
            "Manages Docker container networking",
            "Locks files on disk to prevent concurrent writes"
        ],
        "correct_index": 0,
        "explanation": "The GIL is a mutex that protects access to Python objects, preventing multiple threads from executing Python bytecodes at once in CPython."
    },
    {
        "difficulty": "medium",
        "question": "What is the time complexity of searching for an element in a balanced Binary Search Tree (BST)?",
        "options": [
            "O(1)",
            "O(log n)",
            "O(n)",
            "O(n log n)"
        ],
        "correct_index": 1,
        "explanation": "In a balanced BST, each step cuts the remaining search space in half, resulting in O(log n) time complexity."
    },
    {
        "difficulty": "medium",
        "question": "What Docker flag is used to isolate a container with zero network access?",
        "options": [
            "--network host",
            "--network none",
            "--network bridge",
            "--no-internet"
        ],
        "correct_index": 1,
        "explanation": "--network none disables all networking interfaces inside the container, enforcing network sandbox isolation."
    },
    {
        "difficulty": "medium",
        "question": "In RESTful API design, what makes an HTTP method 'idempotent'?",
        "options": [
            "Executing the request multiple times produces the same server state as a single execution",
            "The request executes in constant time O(1)",
            "The response is automatically cached by browser CDNs",
            "The endpoint requires OAuth2 bearer authentication"
        ],
        "correct_index": 0,
        "explanation": "Idempotent HTTP methods (like GET, PUT, DELETE) can be called multiple times without producing different side effects."
    },
    {
        "difficulty": "medium",
        "question": "In Python, which dunder method is called when an object is used inside a 'with' context manager statement?",
        "options": [
            "__init__",
            "__enter__",
            "__open__",
            "__start__"
        ],
        "correct_index": 1,
        "explanation": "__enter__() is invoked upon entering a context manager, and __exit__() is invoked upon exiting."
    },
    {
        "difficulty": "medium",
        "question": "Which database normalization form eliminates transitive dependencies between non-key attributes?",
        "options": [
            "First Normal Form (1NF)",
            "Second Normal Form (2NF)",
            "Third Normal Form (3NF)",
            "Boyce-Codd Normal Form (BCNF)"
        ],
        "correct_index": 2,
        "explanation": "3NF requires the table to be in 2NF and that all non-key attributes are directly dependent on the primary key alone."
    },
    {
        "difficulty": "medium",
        "question": "What is the primary difference between a process and a thread in modern operating systems?",
        "options": [
            "Processes share memory space by default, while threads do not",
            "Threads share the parent process's memory space, while processes have separate virtual memory address spaces",
            "Threads can only run on single-core CPUs",
            "Processes cannot communicate via IPC"
        ],
        "correct_index": 1,
        "explanation": "Threads share memory and file descriptors within the same process, whereas processes have isolated virtual address spaces."
    },
    {
        "difficulty": "medium",
        "question": "What is the purpose of the 'temperature' parameter when generating text with Large Language Models?",
        "options": [
            "Controls the hardware CPU clock speed during inference",
            "Controls the randomness and entropy of next-token probability distribution",
            "Sets the maximum number of output tokens generated",
            "Defines the timeout limit for the inference API call"
        ],
        "correct_index": 1,
        "explanation": "Lower temperature (~0.2) makes predictions deterministic and focused, while higher temperature (~0.8) introduces diversity and creativity."
    },
    {
        "difficulty": "medium",
        "question": "Which protocol upgrade enables full-duplex, persistent two-way communication between client and server over a single TCP connection?",
        "options": [
            "HTTP/1.1 Long Polling",
            "WebSocket",
            "gRPC Streaming over UDP",
            "FTP"
        ],
        "correct_index": 1,
        "explanation": "WebSockets upgrade standard HTTP connections into bidirectional, full-duplex channels with minimal message framing overhead."
    },
    {
        "difficulty": "medium",
        "question": "In Python asyncio, what keyword is used to pause coroutine execution until an awaitable task completes?",
        "options": [
            "yield from",
            "await",
            "defer",
            "async"
        ],
        "correct_index": 1,
        "explanation": "The 'await' keyword yields control back to the event loop until the awaited coroutine or Future resolves."
    },
    {
        "difficulty": "medium",
        "question": "What does CORS (Cross-Origin Resource Sharing) enforce in web browsers?",
        "options": [
            "Prevents web pages from making API requests to a different domain unless explicitly permitted by the server's headers",
            "Enforces HTTPS encryption on all outgoing requests",
            "Blocks third-party tracking cookies automatically",
            "Compresses images before uploading to cloud CDNs"
        ],
        "correct_index": 0,
        "explanation": "CORS headers (such as Access-Control-Allow-Origin) allow servers to declare which external origins can access their resources."
    },
    {
        "difficulty": "medium",
        "question": "Which cryptographic hash function produces a 256-bit (32-byte) digest and is standard in Bitcoin and TLS certificates?",
        "options": [
            "MD5",
            "SHA-1",
            "SHA-256",
            "CRC32"
        ],
        "correct_index": 2,
        "explanation": "SHA-256 is a member of the SHA-2 cryptographic hash family designed by the NSA and widely used for integrity and signatures."
    },
    {
        "difficulty": "medium",
        "question": "What does a reverse proxy like Nginx or Caddy primarily do?",
        "options": [
            "Routes incoming client requests from the internet to internal backend services and handles SSL termination",
            "Intercepts client outbound traffic to cache local ISP web pages",
            "Directs database read queries to read-only replica nodes",
            "Generates SSL certificates on the client browser"
        ],
        "correct_index": 0,
        "explanation": "A reverse proxy accepts incoming traffic on public ports (80/443), terminates SSL, and forwards requests to local backend services."
    },

    # HARD TIER
    {
        "difficulty": "hard",
        "question": "In PostgreSQL, which index type is specifically optimized for vector similarity search using cosine distance?",
        "options": [
            "B-Tree",
            "HNSW / IVFFlat (pgvector)",
            "GiST",
            "BRIN"
        ],
        "correct_index": 1,
        "explanation": "The pgvector extension uses HNSW (Hierarchical Navigable Small World) and IVFFlat indexes to accelerate vector cosine and L2 distance searches."
    },
    {
        "difficulty": "hard",
        "question": "In Python, which built-in function returns an iterator of tuples containing counts and values?",
        "options": [
            "zip()",
            "enumerate()",
            "map()",
            "filter()"
        ],
        "correct_index": 1,
        "explanation": "enumerate(iterable, start=0) yields (index, item) tuples as an iterator without loading the full list in memory."
    },
    {
        "difficulty": "hard",
        "question": "What is the key difference between HNSW (Hierarchical Navigable Small World) and IVFFlat in vector databases?",
        "options": [
            "HNSW builds a multi-layer proximity graph offering higher recall at the cost of more memory, while IVFFlat uses Voronoi cell clustering",
            "IVFFlat is an exact brute-force search, while HNSW is only for text strings",
            "HNSW requires GPU acceleration, while IVFFlat only works on disk",
            "IVFFlat cannot calculate cosine similarity"
        ],
        "correct_index": 0,
        "explanation": "HNSW constructs a multi-layer geometric graph for ultra-fast high-recall vector search, whereas IVFFlat clusters vectors into inverted lists."
    },
    {
        "difficulty": "hard",
        "question": "In transformer neural networks, what mathematical operation scales the dot-product attention in Self-Attention?",
        "options": [
            "Dividing by the square root of the key dimension (sqrt(d_k))",
            "Multiplying by the batch size",
            "Applying Sigmoid activation to raw query weights",
            "Calculating the Frobenius norm of the value matrix"
        ],
        "correct_index": 0,
        "explanation": "Scaled Dot-Product Attention divides Q * K^T by sqrt(d_k) to prevent dot products from growing excessively large for large dimensions."
    },
    {
        "difficulty": "hard",
        "question": "In Linux systems programming, what is the key difference between the 'fork()' and 'execve()' system calls?",
        "options": [
            "fork() creates a child clone of the calling process, while execve() replaces the current process image with a new executable",
            "fork() terminates a process, while execve() spawns a new thread",
            "execve() creates a shared memory segment, while fork() locks the filesystem",
            "fork() is a user-space library function, while execve() runs on GPU hardware"
        ],
        "correct_index": 0,
        "explanation": "fork() creates an exact copy of the process address space via Copy-On-Write (COW), whereas execve() replaces the process memory with a new binary."
    },
    {
        "difficulty": "hard",
        "question": "What is the CAP Theorem trade-off in distributed database systems during a network partition (P)?",
        "options": [
            "You must choose between Consistency (C) and Availability (A)",
            "You must choose between Performance (P) and Durability (D)",
            "You must choose between Atomicity (A) and Isolation (I)",
            "You can achieve 100% Consistency, Availability, and Partition tolerance simultaneously"
        ],
        "correct_index": 0,
        "explanation": "Brewer's CAP Theorem states that when a network partition (P) occurs, a distributed system must sacrifice either Consistency or Availability."
    },
    {
        "difficulty": "hard",
        "question": "In Rust, what mechanism guarantees memory safety at compile time without a garbage collector?",
        "options": [
            "Reference counting with automatic cycle detection",
            "Ownership system with Borrow Checker and explicit lifetimes",
            "Virtual memory page protection hooks",
            "Runtime heap compaction"
        ],
        "correct_index": 1,
        "explanation": "Rust enforces strict ownership, borrowing (aliasing XOR mutability), and compile-time lifetime analysis to prevent data races and memory leaks."
    },
    {
        "difficulty": "hard",
        "question": "Why is 'hmac.compare_digest()' used instead of standard '==' comparison when validating API tokens or password hashes?",
        "options": [
            "It runs in constant time to prevent timing side-channel attacks",
            "It automatically decrypts RSA ciphertext",
            "It compresses large strings before comparing",
            "It generates a SHA-512 checksum on the fly"
        ],
        "correct_index": 0,
        "explanation": "Standard string equality returns false on the first mismatched byte, leaking character match timing. Constant-time comparison prevents timing attacks."
    },
    {
        "difficulty": "hard",
        "question": "What is the primary role of the 'Epoll' system call in the Linux kernel used by high-concurrency event loops (like Node.js and Uvicorn)?",
        "options": [
            "It monitors multiple file descriptors for I/O readiness in O(1) time complexity",
            "It allocates memory directly on NVMe flash chips",
            "It compiles Python bytecode into C extensions",
            "It schedules CPU threads across multiple NUMA nodes"
        ],
        "correct_index": 0,
        "explanation": "Epoll scales O(1) with the number of monitored file descriptors by registering events in kernel space rather than polling every descriptor linearly like select/poll."
    },
    {
        "difficulty": "hard",
        "question": "In modern LLM quantization, what does 'AWQ' (Activation-aware Weight Quantization) do to achieve 4-bit weights with minimal loss?",
        "options": [
            "Protects the 1% most salient weight channels based on activation magnitudes while quantizing the rest to 4-bit integers",
            "Converts all floating point tensors to 8-bit characters",
            "Prunes 50% of the attention heads completely",
            "Re-trains the embedding layers from scratch on a synthetic corpus"
        ],
        "correct_index": 0,
        "explanation": "AWQ identifies that not all weights are equally important: by preserving salient weights determined by observation of activations, it dramatically reduces quantization error."
    }
]

async def generate_trivia_question(guild_id: str = "global", difficulty: str = "medium") -> Dict[str, Any]:
    if guild_id and guild_id != "global":
        try:
            lore_items = await search_server_lore(guild_id, query_text="rule fact history", top_k=3)
            if lore_items and len(lore_items) > 0:
                selected_lore = random.choice(lore_items)
                fact_text = selected_lore.get("content", "")
                if fact_text:
                    return {
                        "question": "🧠 [Server Lore Trivia]: What fact is recorded about this server?",
                        "options": [
                            fact_text[:100],
                            "The server was founded in 1995.",
                            "All bot commands require superuser privileges.",
                            "The community strictly forbids discussing code."
                        ],
                        "correct_index": 0,
                        "explanation": f"This server lore fact was recorded under [{selected_lore.get('source_type', 'lore').upper()}].",
                        "difficulty": difficulty
                    }
        except Exception as e:
            logger.warning(f"Could not fetch server lore trivia: {e}")

    filtered = [q for q in TECH_TRIVIA_BANK if q.get("difficulty") == difficulty]
    return random.choice(filtered) if filtered else random.choice(TECH_TRIVIA_BANK)
