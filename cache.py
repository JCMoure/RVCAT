import numpy as np

class Cache:

  def __init__(self, cache_sz, block_sz, MissLatency= 10, MissIssueTime= 4,
               record_requests=False):

    self.CACHE_SIZE      = cache_sz
    self.BLOCK_SIZE      = block_sz

    self.MEM_latency     = MissLatency
    self.MEM_issue_time  = MissIssueTime
    self.record_requests = record_requests

    self.TAGS     = np.zeros( cache_sz, dtype=np.uint32)
    self.DATA     = np.zeros( cache_sz, dtype=np.uint32)
    self.LRU      = np.zeros( cache_sz, dtype=np.uint32)
    self.VALID    = np.zeros( cache_sz, dtype=np.uint32)
    self.MODIFIED = np.zeros( cache_sz, dtype=np.uint32)

    self.reset()

  def reset(self):
    self.MEM_last_access = - self.MEM_issue_time
    self.MEM_requests = []

    # Initialize cache with LRU list: any random order would suffice
    for i in range(self.CACHE_SIZE):
      self.LRU[i]     = i
      self.VALID[i]   = 0

  # returns position in cache where block resides, or -1 otherwise
  def search(self, block):
    for i in range(self.CACHE_SIZE):
      if self.VALID[i]==1 and self.TAGS[i]==block:
        return i
    return -1

  # updates the LRU list setting cache position pos at the end
  def updateLRU(self, block):
    previous = self.LRU[block]
    for i in range(self.CACHE_SIZE):
      if self.LRU[i] > previous:
        self.LRU[i] = self.LRU[i]-1      # Decrease LRU priority
    self.LRU[block] = self.CACHE_SIZE-1  # Set maximum priority

  # get line with LRU=0
  def getLRU(self):
    for i in range(self.CACHE_SIZE):
      if self.LRU[i] == 0:
        return i
    return 0  ## Error: should not happen (but not checked at runtime)

  def get_state(self, current_cycle):
    return [
      {
        "line": line,
        "valid": bool(self.VALID[line]),
        "address": int(self.TAGS[line]) * self.BLOCK_SIZE if self.VALID[line] else None,
        "dirty": bool(self.MODIFIED[line]) if self.VALID[line] else False,
        "lru": int(self.LRU[line]),
        "ready_cycle": int(self.DATA[line]) if self.VALID[line] else None,
        "loading": bool(self.VALID[line] and self.DATA[line] > current_cycle),
      }
      for line in range(self.CACHE_SIZE)
    ]

  def access(self, access_type, address, current_cycle, instruction_index=None):
    # returns result (0: hit, 1: primary miss, 2: secondary miss, 3: primary miss with MM update of dirty block),
    #         latency (hit: 0, primary miss: latency_to_MM_request_sent, secondary miss: latency_to_WB),

    block   = address // self.BLOCK_SIZE
    pos     = self.search(block)
    cache_hit = pos >= 0
    result  = 0  # HIT by default
    latency = 0  # HIT latency by default
      
    if (pos >= 0): 
      if self.DATA[pos] > current_cycle:  # SECONDARY MISS
        result  = 2  # CACHE_2ND
        latency = int(self.DATA[pos]) + 1 - current_cycle
        self.DATA[pos] += 1     # one secondary miss to same cache line per cycle
      # else: HIT, no latency

    else:  # PRIMARY MISS
      result = 1 # CACHE_MISS

      pos = self.getLRU()
      # compute traffic to Main Memory
      self.MEM_last_access += self.MEM_issue_time

      if current_cycle > self.MEM_last_access:
        self.MEM_last_access = current_cycle

      latency = self.MEM_last_access - current_cycle ## self.MEM_latency will be added by scheduler
      if self.record_requests:
        self.MEM_requests.append({
          "cycle": int(self.MEM_last_access),
          "address": int(block * self.BLOCK_SIZE),
          "operation": "read" if access_type == 0 else "read_for_write",
          "instruction_index": instruction_index,
          "duration": int(self.MEM_issue_time),
        })

      if (self.MODIFIED[pos] == 1):   # Need to update dirty data block in Cache to Memory
        self.MEM_last_access  += self.MEM_issue_time  # consume MEM bandwidth
        if self.record_requests:
          self.MEM_requests.append({
            "cycle": int(self.MEM_last_access),
            "address": int(self.TAGS[pos]) * self.BLOCK_SIZE,
            "operation": "write",
            "instruction_index": instruction_index,
            "duration": int(self.MEM_issue_time),
          })
        result = 3  # CACHE_MISS_WB
  
      self.TAGS[pos]  = block    # store tag for stored block
      self.VALID[pos] = 1        # cache line is valid
      self.DATA[pos]  = current_cycle + latency + self.MEM_latency  # time when data will be ready in cache

    if cache_hit:
      if access_type == 1:
        self.MODIFIED[pos] = 1
    else:
      self.MODIFIED[pos] = access_type
    self.updateLRU(pos)  
    return result, latency