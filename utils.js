function formatTimeWithoutSeconds(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  let timeString = '';
  if (hours > 0) {
    timeString += `${hours} hour${hours !== 1 ? 's' : ''}`;
  }
  if (minutes > 0) {
    if (timeString) timeString += ' ';
    timeString += `${minutes} minute${minutes !== 1 ? 's' : ''}`;
  }

  return timeString || '0 minutes';
}