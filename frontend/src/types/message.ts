export type Sender = 'user' | 'agent';

export type MessageCardProps = {
	id: string,
	text: string,
	sender: Sender,
	timestamp?: Date,
}
