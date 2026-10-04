import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
content = open('frontend/index.html', encoding='utf-8').read()
print('File size:', len(content), 'bytes')

fns = [
    'REPLAY_EPISODES_DATA', 'generateCrisisJourney', 'renderCustReplayChart',
    '_renderReplayBarChart', '_renderReplayJourneyChart', 'selectCustReplayEpisode',
    'cust-replay-journey-chart', 'cust-replay-journey-wrap', 'barrierExplain', 'bufferMargin'
]
for fn in fns:
    count = content.count(fn)
    print(f'  {fn}: {count} occurrence(s)')
