def overlaps(event1, event2):
    return not (event1.end_time <= event2.start_time or event2.end_time <= event1.start_time)