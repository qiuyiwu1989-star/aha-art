# Homepage feed memory

Distant tiles retain measured-height lightweight slots and serialized frame markup; an IntersectionObserver with 1400px overscan removes frame/image descendants and restores them on approach. Column positions and existing styles remain intact. Resizing disconnects old observations before rebuilding columns.

In-session homepage state preserves loaded records, final cursor and scroll position when leaving the route. Returning restores that feed rather than restarting at page one. The lightbox itself already leaves the homepage mounted.

Validation: frontend syntax checks passed. Browser long-scroll and return-position acceptance still required; this is not a claim of complete constant-memory virtualization. Slots, serialized markup and loaded metadata grow with browsing; active image/complex frame DOM is reduced. State is session-memory only and does not survive refresh or a separate detail document. No production change.

## Cross-document return

Opening art.html stores compact presentation metadata for already browsed works, the continuation cursor and scroll position, expiring after 30 minutes. Heavy description/analysis payloads are excluded; frame-selection fields are retained. Returning reconstructs the feed without replaying catalog requests. Images remain viewport-windowed. Metadata and lightweight slots still grow with browsing; this is not constant-memory virtualization. Browser sessionStorage quota failure clears stale state and falls back to browser BFCache; exact reload restoration is not guaranteed when storage is unavailable. No sequential network replay is used.

## Segmented windowing follow-up

Each masonry column now groups 12 works into a measured segment. Distant segments remove every card/frame/image node and retain one height placeholder plus builders using work metadata. No rendered HTML strings are retained. Reverse scrolling reconstructs the segment locally without historical catalog requests. Anchor restoration mounts the target segment before correction. The actual observer callback simulation covers 100 pages / 2400 records / 200 placeholders with four visible segments (48 cards), followed by reverse restoration. This is simulated DOM acceptance, not a browser performance timing claim. Anchor tests include exact viewport delta, wheel cancellation, and route timer cleanup. Metadata and segment count remain proportional to viewed history; heavy DOM is bounded by intersecting viewport segments.
