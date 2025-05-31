from collections import deque

class trackNode:

    def __init__(self):
        self.next = {}
        self.prev = {}

    def __str__(self):
        return f"Node(Prev: {self.prev}, Next: {self.next})"

class trackMap:

    def __init__(self):
        self.trackNodes = {}
        self.numShuffles = 0

    def addTrack(self, trackID, nextID, prevID, shuffleID):
        if trackID not in self.trackNodes:
            self.trackNodes[trackID] = trackNode()

        self.trackNodes[trackID].next[shuffleID] = nextID
        self.trackNodes[trackID].prev[shuffleID] = prevID

        self.numShuffles = max(self.numShuffles, shuffleID)

        
    def findAllPatterns(self, trackID):
        getPrevTrack = lambda curTrackID, shuffleID: self.trackNodes[curTrackID].prev.get(shuffleID, "")
        getNextTrack = lambda curTrackID, shuffleID: self.trackNodes[curTrackID].next.get(shuffleID, "")

        addToPatternPrev = lambda currentPattern, curTrackID: currentPattern.appendleft(curTrackID)
        addToPatternNext = lambda currentPattern, curTrackID: currentPattern.append(curTrackID)

        prevPatterns = self.findPatterns(trackID, getPrevTrack, addToPatternPrev)
        nextPatterns = self.findPatterns(trackID, getNextTrack, addToPatternNext)
        
        print(prevPatterns)
        print(nextPatterns)

        res = {}
        for i in range(0, self.numShuffles):
            res[i] = list(prevPatterns[i])[:-1] + list(nextPatterns[i])

        print(res)

        return res
        

    def findPatterns(self, trackID, getNextTrack, addToPattern):
        shuffleIDToPattern = {}

        self.findPatternsHelper(range(0, self.numShuffles), 
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

        prev = ""
        cur = q.popleft()

        while len(q) > 0:
            next = q.popleft()
            self.addTrack(cur, next, prev, shuffleID)

            prev = cur
            cur = next

        self.addTrack(cur, "", prev, shuffleID)

    def __str__(self):
        """
        Returns a string representation of the entire trackMap.
        """
        if not self.trackNodes:
            return "Track Map is empty."

        map_string_parts = ["--- Track Map State ---"]
        for trackID, node in self.trackNodes.items():
            map_string_parts.append(f"TrackID: {trackID}")
            map_string_parts.append(f"  {node}") 
            map_string_parts.append("-" * 20)
        map_string_parts.append("-----------------------")
        return "\n".join(map_string_parts)

if __name__=="__main__":
    tracks = trackMap()
    tracks.addShuffleQueue(deque(["B","A","D","E","C","F","A"]), 0)
    tracks.addShuffleQueue(deque(["A","D","E","C","B","O","T"]), 1)
    tracks.addShuffleQueue(deque(["B","D","E","C","A","F","W"]), 2)
    tracks.addShuffleQueue(deque(["D","B","E","C","A","F","S"]), 3)
    tracks.addShuffleQueue(deque(["X","D","B","E","C","A","P"]), 4)

    print(tracks)
    tracks.findAllPatterns("C")
    
# Do each side separate
    # go left
    #     each shuffle index keeps track of their best and how many matched
    # go right
    #     each shuffle index keeps track of their best and how many matched
    # combine the left and right for each shuffle