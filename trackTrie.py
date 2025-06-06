from collections import deque

class trackNode:

    def __init__(self):
        self.next = {}
        self.prev = {}

    def __str__(self):
        return f"Node(Prev: {self.prev}, Next: {self.next})"

class TrackTrie:

    def __init__(self):
        self.trackNodes = {}
        self.numShuffles = 0
        self.allPatterns = {}
        self.allTracksWithPatterns = set()

    def addTrack(self, trackID, nextID, prevID, shuffleID):
        if trackID not in self.trackNodes:
            self.trackNodes[trackID] = trackNode()

        self.trackNodes[trackID].next[shuffleID] = nextID
        self.trackNodes[trackID].prev[shuffleID] = prevID

        self.numShuffles = max(self.numShuffles, shuffleID)

    def getAllPatterns(self, shuffleIDs):
        res = []

        for shuffleID in shuffleIDs:
            if shuffleID in self.allPatterns:
                res.append(self.allPatterns[shuffleID])
                
        return res

    def getAllTracksWithPatterns(self):
        return self.allTracksWithPatterns
        
    def findAllPatterns(self, trackID):
        getPrevTrack = lambda curTrackID, shuffleID: self.trackNodes[curTrackID].prev.get(shuffleID, "")
        getNextTrack = lambda curTrackID, shuffleID: self.trackNodes[curTrackID].next.get(shuffleID, "")

        addToPatternPrev = lambda currentPattern, curTrackID: currentPattern.appendleft(curTrackID)
        addToPatternNext = lambda currentPattern, curTrackID: currentPattern.append(curTrackID)

        # both prev and next will share the same IDs since they're populated at the same time
        shuffleIDs = self.getShuffleIDs(trackID)
        
        prevPatterns = self.findPatterns(trackID, getPrevTrack, addToPatternPrev, shuffleIDs)
        nextPatterns = self.findPatterns(trackID, getNextTrack, addToPatternNext, shuffleIDs)

        for shuffleID in shuffleIDs:
            prev = list(prevPatterns.get(shuffleID, []))[:-1]
            next = list(nextPatterns.get(shuffleID, []))
            self.allPatterns[shuffleID] = prev + next

            # Helps in finding songs with patterns from the frontend
            if len(self.allPatterns[shuffleID]) > 1:
                for patternTrackID in self.allPatterns[shuffleID]:
                    self.allTracksWithPatterns.add(patternTrackID)

        return self.allPatterns
        
    def findPatterns(self, trackID, getNextTrack, addToPattern, shuffleIDs):
        shuffleIDToPattern = {}

        self.findPatternsHelper(shuffleIDs, 
                                trackID, 
                                deque(), 
                                shuffleIDToPattern, 
                                getNextTrack, 
                                addToPattern)
        
        return shuffleIDToPattern
    
    def findPatternsHelper(self, shuffleIDs, curTrackID, currentPattern, shuffleIDToPattern, getNextTrack, addToPattern):
        # Base case, no more matches in this shuffleID
        if len(shuffleIDs) == 1:
            return
        
        # we got here, so at least 2 tracks match, which is a pattern!
        addToPattern(currentPattern, curTrackID)

        trackIDToShuffleID = {}

        for shuffleID in shuffleIDs:
            # update the best pattern in this specific shuffle ID
            shuffleIDToPattern[shuffleID] = currentPattern

            # get the next track to look at in this specific shuffle
            nextTrack = getNextTrack(curTrackID, shuffleID)
            
            # means we got to the end of the queue, so nothing more to do
            if nextTrack == "":
                continue
            
            if nextTrack not in trackIDToShuffleID:
                trackIDToShuffleID[nextTrack] = []
                
            trackIDToShuffleID[nextTrack].append(shuffleID)

        # spawn recursive calls for the current patterns
        for trackID, shuffleIDs in trackIDToShuffleID.items():
            self.findPatternsHelper(shuffleIDs, 
                                    trackID, 
                                    deque(currentPattern), 
                                    shuffleIDToPattern, 
                                    getNextTrack, 
                                    addToPattern)

    def addShuffleQueue(self, q:deque, shuffleID):
        if len(q) == 0:
            return
        
        trackIDs = list(q)
        
        prev = ""
        cur = q.popleft()

        while len(q) > 0:
            next = q.popleft()
            self.addTrack(cur, next, prev, shuffleID)

            prev = cur
            cur = next

        self.addTrack(cur, "", prev, shuffleID)

        # only need to check a third of the tracks since each track searches left and right of themselves
        for i in range(0, len(trackIDs) - 1, 3):
            self.findAllPatterns(trackIDs[i])

    def getShuffleQueue(self, shuffleID, trackID):
        q = deque()

        # get everything before the selected track
        cur = trackID
        while cur != "":
            q.appendleft(cur)
            cur = self.trackNodes[cur].prev.get(shuffleID, "")

        # get everything after the selected track
        cur = self.trackNodes[trackID].next.get(shuffleID, "")
        while cur != "":
            q.append(cur)
            cur = self.trackNodes[cur].next.get(shuffleID, "")

        return q
    
    def getShuffleIDs(self, trackID):
        return [key for key in self.trackNodes[trackID].prev]

    def __str__(self):
        if not self.trackNodes:
            return "Track Map is empty."

        map_string_parts = ["--- Track Map State ---"]
        for trackID, node in self.trackNodes.items():
            map_string_parts.append(f"TrackID: {trackID}")
            map_string_parts.append(f"  {node}") 
            map_string_parts.append("-" * 20)
        map_string_parts.append("-----------------------")
        map_string_parts.append("All trackIDs with patterns")
        map_string_parts.append(str(self.allTracksWithPatterns))
        return "\n".join(map_string_parts)

if __name__=="__main__":
    tracks = TrackTrie()
    tracks.addShuffleQueue(deque(["B","A","D","E","C","F","A"]), 0)
    tracks.addShuffleQueue(deque(["A","D","E","C","B","O","T"]), 1)
    tracks.addShuffleQueue(deque(["B","D","E","C","A","F","W"]), 2)
    tracks.addShuffleQueue(deque(["D","B","E","C","A","F","S"]), 3)
    tracks.addShuffleQueue(deque(["X","D","B","E","C","A","P"]), 4)

    print(tracks.getShuffleQueue(4, "B"))
    print(tracks)
    print(str(tracks.allPatterns))
    
# Do each side separate
    # go left
    #     each shuffle index keeps track of their best and how many matched
    # go right
    #     each shuffle index keeps track of their best and how many matched
    # combine the left and right for each shuffle


# we get a new shuffle queue
    # need to find and store all of it's patterns
    # don't need to redo work that was already done, so check the