const pexelsBase = 'https://images.pexels.com/photos';

export const topicImageMap: Record<string, string> = {
  technology: `${pexelsBase}/1089438/pexels-photo-1089438.jpeg?auto=compress&cs=tinysrgb&w=400`,
  vision: `${pexelsBase}/3573965/pexels-photo-3573965.jpeg?auto=compress&cs=tinysrgb&w=400`,
  robotics: `${pexelsBase}/2085844/pexels-photo-2085844.jpeg?auto=compress&cs=tinysrgb&w=400`,
  network: `${pexelsBase}/1142954/pexels-photo-1142954.jpeg?auto=compress&cs=tinysrgb&w=400`,
  art: `${pexelsBase}/2069103/pexels-photo-2069103.jpeg?auto=compress&cs=tinysrgb&w=400`,
  healthcare: `${pexelsBase}/4386466/pexels-photo-4386466.jpeg?auto=compress&cs=tinysrgb&w=400`,
  quantum: `${pexelsBase}/3518299/pexels-photo-3518299.jpeg?auto=compress&cs=tinysrgb&w=400`,
  nature: `${pexelsBase}/957024/forest-trees-perspective-bright-957024.jpeg?auto=compress&cs=tinysrgb&w=400`,
  mechanics: `${pexelsBase}/2591155/pexels-photo-2591155.jpeg?auto=compress&cs=tinysrgb&w=400`,
  security: `${pexelsBase}/60504/security-padlock-lock-detail-60504.jpeg?auto=compress&cs=tinysrgb&w=400`,
  science: `${pexelsBase}/3735429/pexels-photo-3735429.jpeg?auto=compress&cs=tinysrgb&w=400`,
  sound: `${pexelsBase}/994939/pexels-photo-994939.jpeg?auto=compress&cs=tinysrgb&w=400`,
  mathematics: `${pexelsBase}/6237925/pexels-photo-6237925.jpeg?auto=compress&cs=tinysrgb&w=400`,
  connection: `${pexelsBase}/3183150/pexels-photo-3183150.jpeg?auto=compress&cs=tinysrgb&w=400`,
  transportation: `${pexelsBase}/3975385/pexels-photo-3975385.jpeg?auto=compress&cs=tinysrgb&w=400`,
  brain: `${pexelsBase}/3559483/pexels-photo-3559483.jpeg?auto=compress&cs=tinysrgb&w=400`,
  efficiency: `${pexelsBase}/4164056/pexels-photo-4164056.jpeg?auto=compress&cs=tinysrgb&w=400`,
  people: `${pexelsBase}/3184291/pexels-photo-3184291.jpeg?auto=compress&cs=tinysrgb&w=400`,
  data: `${pexelsBase}/590022/pexels-photo-590022.jpeg?auto=compress&cs=tinysrgb&w=400`,
  justice: `${pexelsBase}/6077802/pexels-photo-6077802.jpeg?auto=compress&cs=tinysrgb&w=400`,
};

export function getImageForTopic(keyword: string): string {
  return topicImageMap[keyword] || `${pexelsBase}/1089438/pexels-photo-1089438.jpeg?auto=compress&cs=tinysrgb&w=400`;
}
