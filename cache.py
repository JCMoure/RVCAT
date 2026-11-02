import numpy as np


class Cache:

  def __init__(self, cache_sz, block_sz, MissLatency=10, MissIssueTime=4,
               record_requests=False, fill_buffer_count=2, write_buffer_count=2,
               return_throughput=1):
    for name, count in (
      ("fill_buffer_count", fill_buffer_count),
      ("write_buffer_count", write_buffer_count),
      ("return_throughput", return_throughput),
    ):
      if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 32:
        raise ValueError(f"{name} must be an integer between 1 and 32.")

    self.CACHE_SIZE = cache_sz
    self.BLOCK_SIZE = block_sz
    self.MEM_latency = MissLatency
    self.MEM_issue_time = MissIssueTime
    self.record_requests = record_requests
    self.FILL_BUFFER_COUNT = fill_buffer_count
    self.WRITE_BUFFER_COUNT = write_buffer_count
    self.RETURN_THROUGHPUT = return_throughput

    self.TAGS = np.zeros(cache_sz, dtype=np.uint32)
    self.LRU = np.zeros(cache_sz, dtype=np.uint32)
    self.VALID = np.zeros(cache_sz, dtype=np.uint32)
    self.MODIFIED = np.zeros(cache_sz, dtype=np.uint32)
    self.LOADING = [False] * cache_sz
    self.READY_CYCLE = [None] * cache_sz
    self.reset()

  def reset(self):
    self.next_mm_issue_cycle = 0
    self.MEM_requests = []
    self.mshrs = {}
    self.pending_misses = []
    self.write_buffers = []
    self.mm_queue = []
    self.instruction_requests = {}
    self.fill_buffer_slots = {}
    self.write_buffer_slots = {}
    self.return_waiters_by_line = {}
    self.return_queue = []
    self.returned_instructions = []
    self.last_advance_cycle = None
    self.last_return_cycle = None
    self.protected_lines_this_cycle = set()

    for line in range(self.CACHE_SIZE):
      self.LRU[line] = line
      self.VALID[line] = 0
      self.MODIFIED[line] = 0
      self.LOADING[line] = False
      self.READY_CYCLE[line] = None

  def search(self, block):
    for line in range(self.CACHE_SIZE):
      if self.VALID[line] == 1 and self.TAGS[line] == block:
        return line
    return -1

  def updateLRU(self, line):
    previous = self.LRU[line]
    for index in range(self.CACHE_SIZE):
      if self.LRU[index] > previous:
        self.LRU[index] -= 1
    self.LRU[line] = self.CACHE_SIZE - 1

  def _line_for_miss(self):
    reserved_lines = {entry["line"] for entry in self.mshrs.values()}
    reserved_lines.update(self.return_waiters_by_line)
    candidates = [
      line for line in range(self.CACHE_SIZE)
      if line not in reserved_lines and line not in self.protected_lines_this_cycle
    ]
    if not candidates:
      return None
    return min(candidates, key=lambda line: self.LRU[line])

  def _enqueue_read(self, entry):
    entry["state"] = "queued"
    self.mm_queue.append({
      "operation": entry["operation"],
      "address": entry["address"],
      "duration": self.MEM_issue_time,
      "mshr_block": entry["block"],
      "instruction_indices": [waiter["instruction_index"] for waiter in entry["waiters"]],
    })

  def request_access(self, access_type, address, current_cycle, instruction_index):
    block = address // self.BLOCK_SIZE
    block_address = block * self.BLOCK_SIZE
    line = self.search(block)

    if line >= 0 and not self.LOADING[line]:
      if access_type == 1:
        self.MODIFIED[line] = 1
      self.instruction_requests.pop(instruction_index, None)
      self.updateLRU(line)
      return "hit"

    waiter = {
      "instruction_index": instruction_index,
      "access_type": access_type,
    }

    if block in self.mshrs:
      entry = self.mshrs[block]
      entry["waiters"].append(waiter)
      if "request_record" in entry:
        entry["request_record"]["instruction_indices"].append(instruction_index)
      self.instruction_requests[instruction_index] = {
        "state": entry["state"],
        "block": block,
        "access_type": access_type,
      }
      return "secondary"

    for entry in self.pending_misses:
      if entry["block"] == block:
        entry["waiters"].append(waiter)
        self.instruction_requests[instruction_index] = {
          "state": "queued",
          "block": block,
          "access_type": access_type,
        }
        return "merged"

    self.pending_misses.append({
      "block": block,
      "address": block_address,
      "operation": "read" if access_type == 0 else "read_for_write",
      "waiters": [waiter],
      "requested_cycle": current_cycle,
    })
    self.instruction_requests[instruction_index] = {
      "state": "queued",
      "block": block,
      "access_type": access_type,
    }
    return "miss"

  def get_request_state(self, instruction_index):
    request = self.instruction_requests.get(instruction_index)
    if request is None:
      return None
    if request["state"] in ("return_queue", "returned"):
      return request["state"]
    block = request["block"]
    if block in self.mshrs:
      state = self.mshrs[block]["state"]
      return "waiting_mm" if state == "queued" else state
    entry = next(
      (miss for miss in self.pending_misses if miss["block"] == block),
      None,
    )
    if entry is None or len(self.mshrs) >= self.FILL_BUFFER_COUNT:
      return "queued_fill"
    line = self._line_for_miss()
    if line is None:
      return "queued_line"
    if self.VALID[line] and self.MODIFIED[line] and \
            len(self.write_buffers) >= self.WRITE_BUFFER_COUNT:
      return "queued_write"
    return "queued_fill"

  def consume_completion(self, instruction_index):
    request = self.instruction_requests.get(instruction_index)
    if request is None or request["state"] != "returned":
      return False
    self.instruction_requests.pop(instruction_index)
    line = self.search(request["block"])
    if line >= 0:
      if request["access_type"] == 1:
        self.MODIFIED[line] = 1
      waiters = self.return_waiters_by_line.get(line)
      if waiters is not None:
        waiters.discard(instruction_index)
        if not waiters:
          self.return_waiters_by_line.pop(line)
    return True

  def _admit_pending_misses(self, cycle, writebacks):
    while self.pending_misses and len(self.mshrs) < self.FILL_BUFFER_COUNT:
      entry = self.pending_misses[0]
      line = self._line_for_miss()
      if line is None:
        break

      dirty_victim = bool(self.VALID[line] and self.MODIFIED[line])
      if dirty_victim and len(self.write_buffers) >= self.WRITE_BUFFER_COUNT:
        break

      self.pending_misses.pop(0)
      entry["line"] = line
      entry["state"] = "waiting_writeback" if dirty_victim else "queued"
      self.mshrs[entry["block"]] = entry
      self.fill_buffer_slots[entry["block"]] = self._free_slot(
        self.fill_buffer_slots, self.FILL_BUFFER_COUNT
      )

      if dirty_victim:
        victim_address = int(self.TAGS[line]) * self.BLOCK_SIZE
        writeback = {
          "address": victim_address,
          "operation": "write",
          "duration": self.MEM_issue_time,
          "status": "queued",
          "complete_cycle": None,
          "mshr_block": entry["block"],
        }
        writeback["slot"] = self._free_slot(
          self.write_buffer_slots, self.WRITE_BUFFER_COUNT
        )
        self.write_buffer_slots[victim_address, entry["block"]] = writeback["slot"]
        self.write_buffers.append(writeback)
        self.mm_queue.append({
          "operation": "write",
          "address": victim_address,
          "duration": self.MEM_issue_time,
          "mshr_block": entry["block"],
          "instruction_indices": [],
          "writeback": writeback,
        })
        if entry["waiters"]:
          writebacks.append(entry["waiters"][0]["instruction_index"])

      self.TAGS[line] = entry["block"]
      self.VALID[line] = 1
      self.MODIFIED[line] = 0
      self.LOADING[line] = True
      self.READY_CYCLE[line] = None
      self.updateLRU(line)
      for waiter in entry["waiters"]:
        self.instruction_requests[waiter["instruction_index"]]["state"] = entry["state"]

      if not dirty_victim:
        self._enqueue_read(entry)

  @staticmethod
  def _free_slot(active_slots, count):
    used = set(active_slots.values())
    return next(slot for slot in range(count) if slot not in used)

  def advance(self, cycle):
    writebacks = []
    if cycle != self.last_advance_cycle:
      self.last_advance_cycle = cycle
      self.returned_instructions = []
      self.protected_lines_this_cycle = set()

    completed_writes = [
      writeback for writeback in self.write_buffers
      if writeback["status"] == "inflight"
      and writeback["complete_cycle"] <= cycle
    ]
    for writeback in completed_writes:
      self.write_buffers.remove(writeback)
      self.write_buffer_slots.pop(
        (writeback["address"], writeback["mshr_block"]), None
      )
      entry = self.mshrs.get(writeback["mshr_block"])
      if entry is not None:
        self._enqueue_read(entry)

    completed_fills = [
      entry for entry in self.mshrs.values()
      if entry["state"] == "reading" and entry["ready_cycle"] <= cycle
    ]
    for entry in completed_fills:
      line = entry["line"]
      self.protected_lines_this_cycle.add(line)
      self.LOADING[line] = False
      self.READY_CYCLE[line] = entry["ready_cycle"]
      for waiter in entry["waiters"]:
        instruction_index = waiter["instruction_index"]
        self.instruction_requests[instruction_index]["state"] = "return_queue"
        self.return_queue.append({
          "instruction_index": instruction_index,
          "block": entry["block"],
          "access_type": waiter["access_type"],
        })
        self.return_waiters_by_line.setdefault(line, set()).add(instruction_index)
      self.mshrs.pop(entry["block"])
      self.fill_buffer_slots.pop(entry["block"], None)

    if cycle != self.last_return_cycle:
      self.last_return_cycle = cycle
      self.return_queue.sort(key=lambda waiter: waiter["instruction_index"])
      for waiter in self.return_queue[:self.RETURN_THROUGHPUT]:
        instruction_index = waiter["instruction_index"]
        self.instruction_requests[instruction_index]["state"] = "returned"
        self.returned_instructions.append(instruction_index)
      del self.return_queue[:self.RETURN_THROUGHPUT]

    self._admit_pending_misses(cycle, writebacks)

    if self.mm_queue and cycle >= self.next_mm_issue_cycle:
      request = self.mm_queue.pop(0)
      request["cycle"] = cycle
      self.next_mm_issue_cycle = cycle + max(1, self.MEM_issue_time)
      if request["operation"] == "write":
        writeback = request["writeback"]
        writeback["status"] = "inflight"
        writeback["cycle"] = cycle
        writeback["complete_cycle"] = cycle + max(1, self.MEM_latency)
      else:
        entry = self.mshrs[request["mshr_block"]]
        entry["state"] = "reading"
        entry["ready_cycle"] = cycle + max(1, self.MEM_latency)
        self.READY_CYCLE[entry["line"]] = entry["ready_cycle"]
        for waiter in entry["waiters"]:
          self.instruction_requests[waiter["instruction_index"]]["state"] = "reading"

      if self.record_requests:
        instruction_indices = request["instruction_indices"]
        if request["operation"] != "write":
          entry = self.mshrs[request["mshr_block"]]
          instruction_indices = [
            waiter["instruction_index"] for waiter in entry["waiters"]
          ]
        request_record = {
          "cycle": int(cycle),
          "address": int(request["address"]),
          "operation": request["operation"],
          "instruction_index": instruction_indices[0] if instruction_indices else None,
          "instruction_indices": instruction_indices,
          "duration": int(request["duration"]),
        }
        self.MEM_requests.append(request_record)
        if request["operation"] != "write":
          entry["request_record"] = request_record

    for entry in self.mshrs.values():
      for waiter in entry["waiters"]:
        self.instruction_requests[waiter["instruction_index"]]["state"] = entry["state"]

    return writebacks

  def get_state(self, current_cycle):
    return [
      {
        "line": line,
        "valid": bool(self.VALID[line]),
        "address": int(self.TAGS[line]) * self.BLOCK_SIZE if self.VALID[line] else None,
        "dirty": bool(self.MODIFIED[line]) if self.VALID[line] else False,
        "lru": int(self.LRU[line]),
        "ready_cycle": self.READY_CYCLE[line] if self.VALID[line] else None,
        "loading": bool(self.VALID[line] and self.LOADING[line]),
      }
      for line in range(self.CACHE_SIZE)
    ]

  def get_buffer_state(self):
    fills = [{"slot": slot, "valid": False} for slot in range(self.FILL_BUFFER_COUNT)]
    for block, entry in self.mshrs.items():
      slot = self.fill_buffer_slots[block]
      fills[slot] = {
        "slot": slot,
        "valid": True,
        "address": int(entry["address"]),
        "state": entry["state"],
        "ready_cycle": entry.get("ready_cycle"),
        "instruction_indices": [
          waiter["instruction_index"] for waiter in entry["waiters"]
        ],
      }

    writes = [{"slot": slot, "valid": False} for slot in range(self.WRITE_BUFFER_COUNT)]
    for writeback in self.write_buffers:
      writes[writeback["slot"]] = {
        "slot": writeback["slot"],
        "valid": True,
        "address": int(writeback["address"]),
        "state": writeback["status"],
        "ready_cycle": writeback["complete_cycle"],
      }
    return {"fill": fills, "write": writes}
