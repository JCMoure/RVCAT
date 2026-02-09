import numpy as np

class Cache:

  def __init__(self, cache_sz, block_sz, MissLatency= 10, MissIssueTime= 4):

    self.CACHE_SIZE      = cache_sz
    self.BLOCK_SIZE      = block_sz

    self.MEM_latency     = MissLatency
    self.MEM_issue_time  = MissIssueTime

    self.TAGS     = np.zeros( cache_sz, dtype=np.uint32)
    self.DATA     = np.zeros( cache_sz, dtype=np.uint32)
    self.LRU      = np.zeros( cache_sz, dtype=np.uint32)
    self.VALID    = np.zeros( cache_sz, dtype=np.uint32)
    self.MODIFIED = np.zeros( cache_sz, dtype=np.uint32)

    self.reset()

  def reset(self):
    self.ReadMemoryCount = 0
    self.WriteMemoryCount= 0
    self.CacheReads      = 0
    self.CacheRdMisses   = 0
    self.CacheWrites     = 0
    self.CacheWrMisses   = 0

    self.MEM_last_access = - self.MEM_issue_time

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


  def access(self, access_type, address, current_cycle):  # returns latency

    block   = address // self.BLOCK_SIZE
    pos     = self.search(block)
    latency = 0
    result  = 0  #HIT
    MM_access = -1
      
    if (access_type == 0):
      self.CacheReads  += 1
    else:
      self.CacheWrites += 1

    if (pos >= 0): 
      if self.DATA[pos] > current_cycle:  # SECONDARY MISS
        result  = 2  # CACHE_2ND
        latency = self.DATA[pos] + 1 - current_cycle
        self.DATA[pos] += 1               # one secondary miss to same cache line per cycle

      else:                               # HIT 
        latency = 0

    else:           # PRIMARY MISS
      result = 1 # CACHE_MISS
      if (access_type == 0):
        self.CacheRdMisses += 1
      else:
        self.CacheWrMisses += 1


      pos = self.getLRU()

      # compute traffic to Main Memory
      self.MEM_last_access += self.MEM_issue_time

      if current_cycle > self.MEM_last_access:
        self.MEM_last_access = current_cycle

      latency = self.MEM_last_access - current_cycle + self.MEM_latency

      if (self.MODIFIED[pos] == 1):
        self.WriteMemoryCount += 1                    # Copy data block in Cache to Memory
        self.MEM_last_access  += self.MEM_issue_time  # consume MEM bandwidth
       
      self.ReadMemoryCount += 1      # Copy data block from Memory to Cache

      self.TAGS[pos]  = block    # store tag for stored block
      self.VALID[pos] = 1        # cache line is valid
      self.DATA[pos]  = current_cycle + latency
      MM_access       = self.MEM_last_access

    self.MODIFIED[pos] = access_type
    self.updateLRU(pos)  
    return latency, result, MM_access


  def statistics(self, cycles):
      MM_Reads        = self.ReadMemoryCount
      MM_transactions = MM_Reads + self.WriteMemoryCount
      MM_trans_time   = MM_transactions * self.MEM_issue_time
      if MM_trans_time > cycles:
          # this is due to actions happening after timeline window
          MM_transactions = cycles // self.MEM_issue_time
          if MM_Reads > MM_transactions:
              MM_Reads = MM_transactions

      MM_trans_time   = MM_transactions * self.MEM_issue_time
      MM_read_time    = MM_Reads * self.MEM_issue_time

      return MM_trans_time/cycles, MM_read_time/cycles, self.CacheRdMisses, self.CacheWrMisses


  def state(self):
    print("*********************************************************************")
    print("**               Block Size= ", self.BLOCK_SIZE, "          **")
    for i in range(self.CACHE_SIZE):
      print("* Line", i, "VALID=", self.VALID[i], "LRU=", self.LRU[i], "MODIF=", self.MODIFIED[i], "TAG=", self.TAGS[i], "  **")
    print("*********************************************************************")
